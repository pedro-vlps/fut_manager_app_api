"""Fluxos HTTP transacionais; registros revertidos ao final de cada teste."""
import unittest
from uuid import uuid4
from types import SimpleNamespace
from src.models.entities import Profile
from src.models.championships import Club, ClubMember, Championship, ChampionshipEntry, ChampionshipPlayer
from src.routers.championships import router
from src.helpers.championships import initial_fixtures, qualified_pairs
from tests.test_auth import AuthTestCase


class ChampionshipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = AuthTestCase.asyncSetUp
    asyncTearDown = AuthTestCase.asyncTearDown
    login = AuthTestCase.login

    async def test_twelve_teams_custom_groups_semifinals_and_final(self):
        await self.setup_api()
        for format in ('knockout', 'cascade'):
            response = await self.client.post('/championships', headers=self.headers,
                json={'name': 'Copa', 'season': '2026', 'capacity': 12, 'format': format})
            self.assertEqual(response.status_code, 422)
        cup = await self.create_cup(12, 'groups_knockout')
        await self.fill_cup(cup)
        base = f"/championships/{cup['id']}"
        data = (await self.client.get(base, headers=self.headers)).json()
        ids = [entry['club_id'] for entry in data['entries']]
        groups = [ids[i::4] for i in range(4)]
        payload = {'groups': groups}
        self.assertEqual((await self.client.post(base + '/groups', headers=self.other_headers, json=payload)).status_code, 403)
        for invalid in [groups[:3], [ids[:4], ids[4:8], ids[8:]], [[ids[0]] * 3] * 4,
                        [[str(uuid4()), *groups[0][1:]], *groups[1:]]]:
            response = await self.client.post(base + '/groups', headers=self.headers, json={'groups': invalid})
            self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.post(base + '/groups', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        # As seeds e os elencos não mudam quando a divisão dos grupos muda.
        self.assertEqual([(e['seed'], e['players']) for e in response.json()['entries']],
                         [(e['seed'], e['players']) for e in data['entries']])
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        self.assertEqual(len(data['matches']), 12)
        # Permite corrigir os grupos depois do início, antes de qualquer registro.
        response = await self.client.post(base + '/groups', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        for index, group in enumerate(groups):
            games = [m for m in data['matches'] if m['pool'] == chr(65 + index)]
            self.assertEqual(len(games), 3)
            self.assertEqual({team for m in games for team in (m['home_id'], m['away_id'])}, set(group))
            self.assertTrue(all(sum(team in (m['home_id'], m['away_id']) for m in games) == 2 for team in group))
        for match in list(data['matches']):
            response = await self.client.post(base + f"/matches/{match['id']}/score", headers=self.headers,
                json={'home_score': 0, 'away_score': 0})
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
        self.assertEqual((await self.client.post(base + '/groups', headers=self.headers, json=payload)).status_code, 409)
        semifinals = [m for m in data['matches'] if m['stage'] == 'knockout']
        self.assertEqual([(m['home_id'], m['away_id']) for m in semifinals],
                         [(groups[0][0], groups[1][0]), (groups[2][0], groups[3][0])])
        self.assertEqual(len(semifinals), 2)
        while data['status'] != 'finished':
            match = next(m for m in data['matches'] if m['home_score'] is None)
            response = await self.client.post(base + f"/matches/{match['id']}/score", headers=self.headers,
                json={'home_score': 0, 'away_score': 0, 'winner_id': match['home_id']})
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
        self.assertEqual(len(data['matches']), 15)
        self.assertEqual(data['champion_id'], groups[0][0])
        self.assertTrue(any(t['category'] == 'championship_champion' for t in data['trophies']))

    async def test_group_changes_protect_match_records_and_other_formats(self):
        await self.setup_api()
        for capacity in (4, 8, 16):
            cup = await self.create_cup(capacity, 'groups_knockout')
            await self.fill_cup(cup)
            base = f"/championships/{cup['id']}"
            data = (await self.client.get(base, headers=self.headers)).json()
            ids = [e['club_id'] for e in reversed(data['entries'])]
            payload = {'groups': [ids[i:i + 4] for i in range(0, capacity, 4)]}
            self.assertEqual((await self.client.post(base + '/groups', headers=self.headers, json=payload)).status_code, 200)
            data = (await self.client.post(base + '/start', headers=self.headers)).json()
            match = data['matches'][0]
            keeper = next(e['players'][0]['id'] for e in data['entries'] if e['club_id'] == match['home_id'])
            response = await self.client.post(base + f"/matches/{match['id']}/goalkeepers", headers=self.headers,
                json={'home_goalkeeper_id': keeper})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual((await self.client.post(base + '/groups', headers=self.headers, json=payload)).status_code, 409)
            persisted = (await self.client.get(base, headers=self.headers)).json()
            self.assertEqual(persisted['matches'][0]['id'], match['id'])
            self.assertEqual(persisted['matches'][0]['home_goalkeeper_id'], keeper)
        cup = await self.create_cup()
        self.assertEqual((await self.client.post(f"/championships/{cup['id']}/groups", headers=self.headers,
            json={'groups': [[str(uuid4())]]})).status_code, 409)

    async def test_home_and_away_only_finishes_after_both_legs(self):
        await self.setup_api()
        payload = dict(name='Liga ida e volta', season='2026', capacity=4, format='league', home_and_away=True)
        for format in ('knockout', 'groups_knockout', 'cascade'):
            invalid = await self.client.post('/championships', headers=self.headers, json={**payload, 'format': format})
            self.assertEqual(invalid.status_code, 422, invalid.text)
        response = await self.client.post('/championships', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        cup = response.json()
        self.assertTrue(cup['home_and_away'])
        await self.fill_cup(cup)
        base = f"/championships/{cup['id']}"
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        self.assertEqual(len(data['matches']), 12)
        self.assertEqual({m['round'] for m in data['matches']}, set(range(1, 7)))
        # Confirmar o primeiro turno não pode definir campeão nem distribuir troféus.
        for match in data['matches']:
            response = await self.client.post(base + f"/matches/{match['id']}/score", headers=self.headers,
                json=dict(home_score=0, away_score=0, action_ids=[]))
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            if match['sequence'] == 6:
                self.assertEqual(data['status'], 'in_progress')
                self.assertIsNone(data['champion_id'])
                self.assertEqual(data['trophies'], [])
                self.assertTrue(all(row['played'] == 3 for row in data['general_standings']))
        self.assertEqual(data['status'], 'finished')
        self.assertEqual(data['champion_id'], data['general_standings'][0]['club_id'])
        self.assertTrue(all(row['played'] == 6 for row in data['general_standings']))
        self.assertTrue(data['trophies'])


    async def test_league_allows_actions_and_results_in_later_rounds_first(self):
        await self.setup_api()
        cup = await self.create_cup(format='league')
        await self.fill_cup(cup)
        base = f"/championships/{cup['id']}"
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        match = data['matches'][-1]
        self.assertEqual(match['round'], 3)
        home = next(e for e in data['entries'] if e['club_id'] == match['home_id'])
        action = dict(id=str(uuid4()), team_id=home['club_id'], presence_id=home['players'][0]['id'], action_type='goal')
        url = base + f"/matches/{match['id']}"
        response = await self.client.post(url + '/actions', headers=self.headers, json=action)
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.client.post(url + '/score', headers=self.headers,
            json=dict(home_score=1, away_score=0, action_ids=[action['id']]))
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['status'], 'in_progress')
        self.assertIsNone(data['matches'][0]['home_score'])
        self.assertEqual(data['matches'][-1]['home_score'], 1)

    async def test_match_actions_persist_validate_and_drive_result(self):
        await self.setup_api()
        cup = await self.create_cup(format='cascade')
        await self.fill_cup(cup)
        base = f"/championships/{cup['id']}"
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        match, later = data['matches'][:2]
        url = base + f"/matches/{match['id']}"
        home = next(e for e in data['entries'] if e['club_id'] == match['home_id'])
        away = next(e for e in data['entries'] if e['club_id'] == match['away_id'])
        keepers = {'home_goalkeeper_id': home['players'][1]['id'], 'away_goalkeeper_id': away['players'][1]['id']}
        self.assertEqual((await self.client.post(url + '/goalkeepers', json=keepers)).status_code, 401)
        self.assertEqual((await self.client.post(url + '/goalkeepers', headers=self.other_headers, json=keepers)).status_code, 403)
        self.assertEqual((await self.client.post(url + '/goalkeepers', headers=self.headers,
            json={**keepers, 'home_goalkeeper_id': away['players'][0]['id']})).status_code, 422)
        self.assertEqual((await self.client.post(url + '/goalkeepers', headers=self.headers, json=keepers)).status_code, 200)
        goal = dict(id=str(uuid4()), team_id=home['club_id'], presence_id=home['players'][0]['id'], action_type='goal')
        self.assertEqual((await self.client.post(url + '/actions', json=goal)).status_code, 401)
        self.assertEqual((await self.client.post(url + '/actions', headers=self.other_headers, json=goal)).status_code, 403)
        self.assertEqual((await self.client.post(base + f"/matches/{later['id']}/actions", headers=self.headers, json=goal)).status_code, 409)
        self.assertEqual((await self.client.post(url + '/actions', headers=self.headers, json={**goal, 'presence_id': away['players'][0]['id']})).status_code, 422)
        self.assertEqual((await self.client.post(url + '/actions', headers=self.headers, json={**goal, 'team_id': str(uuid4())})).status_code, 422)
        for _ in range(2):
            response = await self.client.post(url + '/actions', headers=self.headers, json=goal)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()['matches'][0]['actions']), 1)
        self.assertEqual((await self.client.post(url + '/actions', headers=self.headers, json={**goal, 'action_type': 'assist'})).status_code, 409)
        events = [goal]
        for kind, team, player in [('assist', home, 1), ('own_goal', away, 0), ('yellow_card', home, 0), ('red_card', away, 1)]:
            event = dict(id=str(uuid4()), team_id=team['club_id'], presence_id=team['players'][player]['id'], action_type=kind)
            response = await self.client.post(url + '/actions', headers=self.headers, json=event)
            self.assertEqual(response.status_code, 200, response.text)
            events.append(event)
        saved = (await self.client.get(base, headers=self.other_headers)).json()['matches'][0]
        self.assertEqual([a['id'] for a in saved['actions']], [a['id'] for a in events])
        self.assertIsNone(saved['home_score'])
        pending_rankings = (await self.client.get(base, headers=self.headers)).json()['player_rankings']
        self.assertTrue(all(p['matches'] == p['yellow_cards'] == p['red_cards'] == p['goals_conceded'] == 0 for p in pending_rankings))
        removal = url + f"/actions/{events[-1]['id']}/remove"
        self.assertEqual((await self.client.post(removal, headers=self.other_headers)).status_code, 403)
        for _ in range(2):
            self.assertEqual((await self.client.post(removal, headers=self.headers)).status_code, 200)
        payload = dict(home_score=2, away_score=0, action_ids=[e['id'] for e in events])
        self.assertEqual((await self.client.post(url + '/score', headers=self.headers, json=payload)).status_code, 409)
        payload['action_ids'].pop()
        self.assertEqual((await self.client.post(url + '/score', headers=self.headers, json={**payload, 'home_score': 3})).status_code, 422)
        response = await self.client.post(url + '/score', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        finished = response.json()
        self.assertEqual(finished['matches'][0]['home_score'], 2)
        self.assertTrue(finished['matches'][0]['statistics_complete'])
        ranking = {p['profile_id']: p for p in finished['player_rankings']}
        self.assertEqual(ranking[home['players'][0]['id']]['goals'], 1)
        self.assertEqual(ranking[home['players'][1]['id']]['assists'], 1)
        self.assertEqual(ranking[away['players'][0]['id']]['own_goals'], 1)
        self.assertEqual(ranking[home['players'][0]['id']]['yellow_cards'], 1)
        self.assertEqual(ranking[home['players'][1]['id']]['goalkeeper_matches'], 1)
        self.assertEqual(ranking[home['players'][1]['id']]['goals_conceded'], 0)
        self.assertEqual(ranking[away['players'][1]['id']]['goals_conceded'], 2)
        self.assertEqual(ranking[away['players'][1]['id']]['goalkeeper_matches'], 1)
        self.assertEqual(ranking[away['players'][0]['id']]['losses'], 1)
        self.assertEqual(ranking[away['players'][1]['id']]['red_cards'], 0)
        self.assertEqual((await self.client.post(url + '/goalkeepers', headers=self.headers, json=keepers)).status_code, 409)
        self.assertEqual((await self.client.post(url + '/actions', headers=self.headers, json={**goal, 'id': str(uuid4())})).status_code, 409)
        self.assertEqual((await self.client.post(removal, headers=self.headers)).status_code, 409)

    async def test_action_score_allows_group_draw_and_requires_knockout_tiebreak(self):
        await self.setup_api()
        for format in ['groups_knockout', 'knockout']:
            cup = await self.create_cup(format=format)
            await self.fill_cup(cup)
            base = f"/championships/{cup['id']}"
            data = (await self.client.post(base + '/start', headers=self.headers)).json()
            match = data['matches'][0]
            url = base + f"/matches/{match['id']}/score"
            payload = dict(home_score=0, away_score=0, action_ids=[])
            if format == 'knockout':
                self.assertEqual((await self.client.post(url, headers=self.headers, json=payload)).status_code, 422)
                payload['winner_id'] = match['home_id']
            response = await self.client.post(url, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['matches'][0]['winner_id'], payload.get('winner_id'))

    async def test_invitation_code_discovery_and_registration(self):
        await self.setup_api()
        first = await self.create_cup()
        second = await self.create_cup()
        self.assertRegex(first['code'], r'^[A-Z0-9]{6}$')
        self.assertNotEqual(first['code'], second['code'])
        url = '/championship-discovery/search'
        self.assertEqual((await self.client.get(url, params={'code': first['code']})).status_code, 401)
        self.assertEqual((await self.client.get(url, params={'code': 'bad'}, headers=self.headers)).status_code, 422)
        self.assertEqual((await self.client.get(url, params={'code': 'ZZZZZZ'}, headers=self.headers)).status_code, 404)
        found = await self.client.get(url, params={'code': first['code'].lower()}, headers=self.other_headers)
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual(found.json()['id'], first['id'])
        club = await self.create_ready_club(self.other)
        response = await self.client.post(f"/championships/{found.json()['id']}/entries", headers=self.other_headers,
            json={'club_id': str(club.id)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['code'])
        self.assertEqual(len(response.json()['entries']), 1)

    async def test_player_profile_uses_registered_roster_and_hides_private_fields(self):
        await self.setup_api()
        cup = await self.create_cup()
        await self.fill_cup(cup)
        data = (await self.client.get(f"/championships/{cup['id']}", headers=self.headers)).json()
        team, another = data['entries'][:2]
        player_id = team['players'][0]['id']
        url = f"/championships/{cup['id']}/clubs/{team['club_id']}/players/{player_id}"
        self.assertEqual((await self.client.get(url)).status_code, 401)
        response = await self.client.get(url, headers=self.other_headers)
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertEqual(profile['id'], player_id)
        self.assertEqual(profile['name'], team['players'][0]['name'])
        self.assertFalse(profile['can_rate'])
        self.assertIn('positions', profile)
        self.assertIn('trophies', profile)
        self.assertFalse({'email', 'password', 'password_hash', 'rating'} & profile.keys())
        for invalid in [url.replace(team['club_id'], another['club_id']),
                        url.replace(cup['id'], str(uuid4())),
                        url.replace(player_id, str(self.user.id))]:
            self.assertEqual((await self.client.get(invalid, headers=self.headers)).status_code, 404)
        # Mesmo um jogador convidado/aceito depois não entra no elenco já inscrito.
        from uuid import UUID
        from src.models.championships import ClubMember
        self.db.add(ClubMember(club_id=UUID(team['club_id']), profile_id=self.user.id, status='accepted'))
        await self.db.flush()
        self.assertEqual((await self.client.get(url.replace(player_id, str(self.user.id)), headers=self.headers)).status_code, 404)

    async def setup_api(self):
        self.app.include_router(router)
        self.headers = {"Authorization": "Bearer " + (await self.login()).json()["access_token"]}
        self.other_headers = {"Authorization": "Bearer " + (await self.login(self.other, "test-password-456")).json()["access_token"]}

    async def create_cup(self, capacity=4, format="knockout"):
        response = await self.client.post('/championships', headers=self.headers,
            json={"name": "Copa", "season": "2026", "capacity": capacity, "format": format})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def create_ready_club(self, owner, name="Time"):
        club = Club(name=name, owner_id=owner.id)
        teammate = Profile(name="Jogador", email=f"{uuid4()}@example.test", password="test-password-123")
        self.db.add_all([club, teammate])
        await self.db.flush()
        self.db.add_all([ClubMember(club_id=club.id, profile_id=p.id, status="accepted") for p in [owner, teammate]])
        await self.db.flush()
        return club

    async def test_invites_permissions_acceptance_and_roster_snapshot(self):
        await self.setup_api()
        self.assertEqual((await self.client.get('/championships')).status_code, 401)
        self.assertEqual((await self.client.post('/clubs', headers=self.headers, json={"name": "   "})).status_code, 422)
        club = (await self.client.post('/clubs', headers=self.headers, json={"name": "Meu time"})).json()
        cup = await self.create_cup()
        base = f"/championships/{cup['id']}"
        invite_url = f"/clubs/{club['id']}/invitations"
        self.assertEqual((await self.client.post(invite_url, headers=self.other_headers, json={"email": self.user.email})).status_code, 403)
        self.assertEqual((await self.client.post(base + '/entries', headers=self.headers, json={"club_id": club['id']})).status_code, 409)
        for _ in range(2):
            response = await self.client.post(invite_url, headers=self.headers, json={"email": self.other.email.upper()})
            self.assertEqual(response.status_code, 200, response.text)
        invitations = (await self.client.get('/club-invitations', headers=self.other_headers)).json()
        self.assertEqual(len(invitations), 1)
        invitation_url = f"/club-invitations/{invitations[0]['id']}"
        self.assertEqual((await self.client.post(invitation_url, headers=self.headers, json={"accept": True})).status_code, 404)
        self.assertEqual((await self.client.post(invitation_url, headers=self.other_headers, json={"accept": False})).status_code, 204)
        self.assertEqual((await self.client.get('/clubs', headers=self.other_headers)).json(), [])
        await self.client.post(invite_url, headers=self.headers, json={"email": self.other.email})
        self.assertEqual((await self.client.post(invitation_url, headers=self.other_headers, json={"accept": True})).status_code, 204)
        self.assertEqual((await self.client.post(invitation_url, headers=self.other_headers, json={"accept": True})).status_code, 409)
        self.assertEqual((await self.client.post(base + '/entries', headers=self.other_headers, json={"club_id": club['id']})).status_code, 403)
        for _ in range(2):
            response = await self.client.post(base + '/entries', headers=self.headers, json={"club_id": club['id']})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()['entries']), 1)
            self.assertEqual(len(response.json()['entries'][0]['players']), 2)
        second = await self.create_ready_club(self.other)
        self.assertEqual((await self.client.post(base + '/entries', headers=self.other_headers, json={"club_id": str(second.id)})).status_code, 409)
        withdrawal = base + f"/entries/{club['id']}/withdraw"
        self.assertEqual((await self.client.post(withdrawal, headers=self.other_headers)).status_code, 403)
        self.assertEqual((await self.client.post(withdrawal, headers=self.headers)).json()['entries'], [])
        self.assertEqual((await self.client.post(base + '/entries', headers=self.other_headers, json={"club_id": str(second.id)})).status_code, 200)
        other_cup = await self.create_cup()
        self.assertEqual((await self.client.post(f"/championships/{other_cup['id']}/entries", headers=self.headers, json={"club_id": club['id']})).status_code, 200)

    async def fill_cup(self, cup):
        for i in range(cup['capacity']):
            owner = Profile(name=f"Capitão {i}", email=f"{uuid4()}@example.test", password="test-password-123")
            self.db.add(owner)
            await self.db.flush()
            club = await self.create_ready_club(owner, f"Time {i}")
            entry = ChampionshipEntry(championship_id=cup['id'], club_id=club.id, seed=i + 1)
            self.db.add(entry)
            await self.db.flush()
            from src.services.championships import ChampionshipsService
            for member, _ in await ChampionshipsService(self.db).members(club.id):
                self.db.add(ChampionshipPlayer(championship_id=cup['id'], entry_id=entry.id, profile_id=member.profile_id))
        await self.db.flush()

    async def test_all_sizes_and_formats_complete_with_correct_match_counts(self):
        await self.setup_api()
        for capacity in [4, 8, 16]:
            for format in ['knockout', 'groups_knockout', 'league']:
                cup = await self.create_cup(capacity, format)
                base = f"/championships/{cup['id']}"
                self.assertEqual((await self.client.post(base + '/start', headers=self.headers)).status_code, 409)
                await self.fill_cup(cup)
                self.assertEqual((await self.client.post(base + '/start', headers=self.other_headers)).status_code, 403)
                response = await self.client.post(base + '/start', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual((await self.client.post(base + '/start', headers=self.headers)).status_code, 409)
                while data['status'] != 'finished':
                    match = next(m for m in data['matches'] if m['home_score'] is None)
                    url = base + f"/matches/{match['id']}/score"
                    payload = {"home_score": 1, "away_score": 1}
                    if match['stage'] == 'knockout':
                        self.assertEqual((await self.client.post(url, headers=self.headers, json=payload)).status_code, 422)
                        payload['winner_id'] = match['home_id']
                    self.assertEqual((await self.client.post(url, headers=self.other_headers, json=payload)).status_code, 403)
                    response = await self.client.post(url, headers=self.headers, json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    data = response.json()
                    self.assertEqual((await self.client.post(url, headers=self.headers, json=payload)).status_code, 409)
                expected = capacity * (capacity - 1) // 2 if format == 'league' else capacity - 1 if format == 'knockout' else capacity // 4 * 6 + capacity // 2 - 1
                self.assertEqual(len(data['matches']), expected)
                self.assertIsNotNone(data['champion_id'])
                if format == 'league':
                    table = data['general_standings']
                    self.assertEqual(data['champion_id'], table[0]['club_id'])
                    self.assertTrue(all(row['points'] == capacity - 1 and row['draws'] == capacity - 1 for row in table))
                    self.assertTrue(all(m['winner_id'] is None and m['stage'] == 'league' for m in data['matches']))
                    for category, team in [('championship_champion', table[0]['club_id']), ('championship_runner_up', table[1]['club_id'])]:
                        players = next(e['players'] for e in data['entries'] if e['club_id'] == team)
                        self.assertEqual(len([a for a in data['trophies'] if a['category'] == category]), 1)
                else:
                    self.assertEqual(data['champion_id'], data['matches'][-1]['winner_id'])

    async def test_capacity_validation_scope_and_cascade_guard(self):
        await self.setup_api()
        for invalid in [0, 3, 5, 32]:
            self.assertEqual((await self.client.post('/championships', headers=self.headers,
                json={"name": "Copa", "season": "2026", "capacity": invalid, "format": "knockout"})).status_code, 422)
        cup = await self.create_cup()
        await self.fill_cup(cup)
        club = await self.create_ready_club(self.user)
        base = f"/championships/{cup['id']}"
        self.assertEqual((await self.client.post(base + '/entries', headers=self.headers, json={"club_id": str(club.id)})).status_code, 409)
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        self.assertEqual((await self.client.post(base + f'/entries/{club.id}/withdraw', headers=self.headers)).status_code, 409)
        self.assertEqual((await self.client.post(base + '/entries', headers=self.headers, json={"club_id": str(club.id)})).status_code, 409)
        score = {"home_score": 2, "away_score": 0, "winner_id": data['matches'][0]['away_id']}
        url = base + f"/matches/{data['matches'][0]['id']}/score"
        self.assertEqual((await self.client.post(url, headers=self.headers, json=score)).status_code, 422)
        self.assertEqual((await self.client.post(base + f'/matches/{uuid4()}/score', headers=self.headers,
            json={"home_score": 2, "away_score": 0})).status_code, 404)
        cascade = await self.create_cup(format='cascade')
        self.assertEqual((await self.client.post(f"/championships/{cascade['id']}/start", headers=self.headers)).status_code, 409)
        group = await self.client.post('/my-groups', headers=self.headers, json={"name": "Novo grupo"})
        self.assertEqual(group.status_code, 201, group.text)
        self.assertIn(group.json()['id'], [g['id'] for g in (await self.client.get('/auth/me/groups', headers=self.headers)).json()])


class BracketTests(unittest.TestCase):
    def test_groups_advance_crossed_and_seed_breaks_identical_results(self):
        entries = [SimpleNamespace(club_id=i, seed=i + 1) for i in range(8)]
        # UUIDs reais para validação de Standing.
        for entry in entries:
            entry.club_id = uuid4()
        fixtures = initial_fixtures(entries, 'groups_knockout')
        matches = [SimpleNamespace(stage=s, pool=p, home_id=a, away_id=b, home_score=0, away_score=0)
                   for s, _, p, a, b in fixtures]
        pairs = qualified_pairs(entries, matches)
        self.assertEqual(pairs, [(entries[0].club_id, entries[5].club_id), (entries[4].club_id, entries[1].club_id)])
