import unittest
from uuid import UUID, uuid4
from types import SimpleNamespace
from sqlalchemy import text
from cryptography.fernet import InvalidToken
from src.models.privacy import EncryptedText, EncryptedJSON
from src.helpers.privacy import email_lookup
from src.helpers.championships import initial_fixtures
from src.helpers.championship_trophies import trophy_winners
from src.schemas.championships import PlayerRanking
from src.models.entities import PeladaGroup, GroupMember
from src.helpers.passwords import hash_password
from unittest.mock import patch
from src.models.enums import MembershipStatus, GroupRole
from src.routers.groups import router as groups_router
from tests import test_championships as base


class FeedbackRulesTests(unittest.TestCase):
    def test_single_individual_winner_uses_team_placement_for_every_metric(self):
        champion, runner = uuid4(), uuid4()
        rows = [PlayerRanking(profile_id=uuid4(), name='Z', club_id=champion, goals=4, assists=4,
                             goalkeeper_matches=2, goals_conceded=0, team_position=1),
                PlayerRanking(profile_id=uuid4(), name='A', club_id=runner, goals=4, assists=4,
                             goalkeeper_matches=2, goals_conceded=0, team_position=2)]
        individual = [(category, player) for category, player, _ in trophy_winners(rows, champion, runner, True)
                      if category not in ('championship_champion', 'championship_runner_up')]
        self.assertEqual(len(individual), 3)
        self.assertTrue(all(player == rows[0].profile_id for _, player in individual))

    def test_arbitrary_even_and_odd_leagues_have_every_pair_once(self):
        for size in (2, 3, 5, 7, 12, 17):
            entries = [SimpleNamespace(club_id=uuid4(), seed=i+1) for i in range(size)]
            for return_leg in (False, True):
                fixtures = initial_fixtures(entries, 'league', return_leg)
                self.assertEqual(len(fixtures), size*(size-1)*(2 if return_leg else 1)//2)
                rounds = {}
                pairs = {}
                for _, round, _, home, away in fixtures:
                    self.assertNotEqual(home, away)
                    self.assertIsNotNone(home)
                    self.assertIsNotNone(away)
                    rounds.setdefault(round, []).extend((home, away))
                    pair = frozenset((home, away))
                    pairs[pair] = pairs.get(pair, 0) + 1
                self.assertTrue(all(len(teams) == len(set(teams)) for teams in rounds.values()))
                self.assertTrue(all(count == (2 if return_leg else 1) for count in pairs.values()))

    def test_personal_data_randomization_tampering_and_email_index(self):
        field = EncryptedText()
        first = field.process_bind_param('João Silva', None)
        second = field.process_bind_param('João Silva', None)
        self.assertNotEqual(first, second)
        self.assertNotIn('João', first)
        self.assertEqual(field.process_result_value(first, None), 'João Silva')
        with self.assertRaises(InvalidToken):
            field.process_result_value(first[:-8] + 'aaaaaaaa', None)
        self.assertEqual(email_lookup(' USER@example.com '), email_lookup('user@EXAMPLE.com'))
        value = [{'player_name': 'João', 'goals': 2}]
        json_field = EncryptedJSON()
        self.assertEqual(json_field.process_result_value(json_field.process_bind_param(value, None), None), value)


class FeedbackIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.ChampionshipTests.asyncSetUp
    asyncTearDown = base.ChampionshipTests.asyncTearDown
    login = base.ChampionshipTests.login
    setup_api = base.ChampionshipTests.setup_api
    create_cup = base.ChampionshipTests.create_cup
    create_ready_club = base.ChampionshipTests.create_ready_club
    fill_cup = base.ChampionshipTests.fill_cup

    async def start_cup(self, format='knockout', size=4):
        await self.setup_api()
        cup = await self.create_cup(size, format)
        await self.fill_cup(cup)
        self.base = f"/championships/{cup['id']}"
        response = await self.client.post(self.base+'/start', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def post_score(self, match, **payload):
        response = await self.client.post(self.base+f"/matches/{match['id']}/score", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def punishment(self, ids, kind='disqualification', points=0):
        response = await self.client.post(self.base+'/punishments', headers=self.headers,
            json={'club_ids': ids, 'kind': kind, 'points': points, 'reason': 'Infração do regulamento'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_walkover_table_without_player_goals_and_knockout_advance(self):
        for format in ('league', 'groups_knockout', 'knockout', 'cascade'):
            data = await self.start_cup(format)
            match = data['matches'][0]
            data = await self.post_score(match, home_score=99, away_score=99, winner_id=match['home_id'], walkover=True)
            result = data['matches'][0]
            self.assertEqual((result['home_score'], result['away_score']), (3, 0))
            self.assertTrue(result['walkover'] and result['statistics_complete'])
            self.assertTrue(all(p['goals'] == p['assists'] == p['matches'] == p['goals_conceded'] == 0 for p in data['player_rankings']))
            row = next(r for r in data['general_standings'] if r['club_id'] == match['home_id'])
            self.assertEqual((row['points'], row['goals_for']-row['goals_against']), (3, 3))

    async def test_points_penalty_and_disqualification_preserve_past_results(self):
        data = await self.start_cup('league')
        first = data['matches'][0]
        data = await self.post_score(first, home_score=2, away_score=0)
        data = await self.punishment([first['home_id']], 'points', 4)
        row = next(r for r in data['general_standings'] if r['club_id'] == first['home_id'])
        self.assertEqual(row['points'], -1)
        data = await self.punishment([first['home_id']])
        self.assertEqual((data['matches'][0]['home_score'], data['matches'][0]['away_score']), (2, 0))
        future = [m for m in data['matches'][1:] if first['home_id'] in (m['home_id'], m['away_id'])]
        self.assertTrue(all(m['walkover'] and m['winner_id'] != first['home_id'] for m in future))
        self.assertEqual(data['general_standings'][-1]['club_id'], first['home_id'])

    async def test_both_teams_punished_bracket_continues_in_every_format(self):
        for format in ('knockout', 'groups_knockout', 'cascade'):
            data = await self.start_cup(format)
            first = data['matches'][0]
            banned = [first['home_id'], first['away_id']]
            data = await self.punishment(banned)
            for _ in range(20):
                if data['status'] == 'finished':
                    break
                match = next(m for m in data['matches'] if m['home_score'] is None)
                self.assertFalse(set(banned).intersection((match['home_id'], match['away_id'])))
                data = await self.post_score(match, home_score=0, away_score=0,
                    **({'winner_id': match['home_id']} if match['stage'] not in ('league','groups') else {}))
            self.assertEqual(data['status'], 'finished')
            self.assertNotIn(data['champion_id'], banned)
            self.assertEqual(data['matches'][-1]['bracket_size'], 2)

    async def test_random_groups_and_private_championship_code_rotation(self):
        await self.setup_api()
        cup = await self.create_cup(8, 'groups_knockout')
        self.assertEqual((await self.client.post(f"/championships/{cup['id']}/groups/draw", headers=self.headers)).status_code, 409)
        await self.fill_cup(cup)
        self.base = f"/championships/{cup['id']}"
        drawn = await self.client.post(self.base+'/groups/draw', headers=self.headers)
        self.assertEqual(drawn.status_code, 200, drawn.text)
        pools = {}
        for e in drawn.json()['entries']:
            pools[e['pool']] = pools.get(e['pool'], 0) + 1
        self.assertEqual(pools, {'A': 4, 'B': 4})
        outsider = (await self.client.get(self.base, headers=self.other_headers)).json()
        self.assertIsNone(outsider['code'])
        self.assertEqual((await self.client.post(self.base+'/code/rotate', headers=self.other_headers)).status_code, 403)
        rotated = await self.client.post(self.base+'/code/rotate', headers=self.headers)
        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(rotated.json()['code'], cup['code'])
        self.assertEqual((await self.client.get('/championship-discovery/search', params={'code': cup['code']}, headers=self.headers)).status_code, 404)
        feed = await self.client.get('/championship-feed', headers=self.other_headers)
        self.assertEqual(feed.status_code, 200)
        self.assertTrue(any(c['id'] == cup['id'] and c['code'] is None for c in feed.json()))

    async def test_club_code_requires_owner_review_and_trophy_room(self):
        await self.setup_api()
        club = (await self.client.post('/clubs', headers=self.headers, json={'name': 'Time'})).json()
        joined = await self.client.post('/club-discovery/join', headers=self.other_headers, json={'code': club['code']})
        self.assertEqual(joined.status_code, 200)
        members = (await self.client.get('/clubs', headers=self.headers)).json()[0]['members']
        self.assertEqual(next(m['status'] for m in members if m['id'] == str(self.other.id)), 'requested')
        review = await self.client.post(f"/clubs/{club['id']}/members/{self.other.id}/review", headers=self.headers, json={'accept': True})
        self.assertEqual(review.status_code, 200)
        outsider = (await self.client.get('/clubs', headers=self.other_headers)).json()[0]
        self.assertIsNone(outsider['code'])
        self.assertEqual(outsider['trophies'], [])
        data = await self.start_cup()
        while data['status'] != 'finished':
            match = next(m for m in data['matches'] if m['home_score'] is None)
            data = await self.post_score(match, home_score=0, away_score=0, winner_id=match['home_id'])
        trophies = (await self.client.get(f"/clubs/{data['champion_id']}/trophies", headers=self.headers)).json()
        self.assertEqual(trophies[0]['championship_id'], data['id'])
        self.assertEqual(len([t for t in data['trophies'] if t['category'] == 'championship_champion']), 1)

    async def test_database_stores_ciphertext_and_login_survives_reload(self):
        stored = (await self.db.execute(text('SELECT name,email,email_lookup FROM profiles WHERE id=:id'), {'id': self.user.id})).one()
        self.assertTrue(stored.name.startswith('enc:v1:') and stored.email.startswith('enc:v1:'))
        self.assertNotIn(self.user.name, stored.name)
        self.assertEqual(stored.email_lookup, email_lookup(self.user.email))
        self.db.expire(self.user, ['name', 'email'])
        await self.db.refresh(self.user)
        self.assertEqual((await self.login()).status_code, 200)

    async def test_existing_password_hash_is_upgraded_after_login(self):
        with patch('src.helpers.passwords._N', 2**14):
            self.user.password_hash = hash_password('test-password-123')
        await self.db.flush()
        self.assertEqual((await self.login()).status_code, 200)
        self.assertEqual(self.user.password_hash.split('$')[1], str(2**17))

    async def test_group_codes_are_visible_only_to_managers_and_rotate(self):
        await self.setup_api()
        self.app.include_router(groups_router)
        group = PeladaGroup(name='Grupo', created_by_id=self.user.id)
        self.db.add(group)
        await self.db.flush()
        base_url = f'/my-groups/{group.id}'
        first = await self.client.get(base_url, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['group']['code'], group.code)
        self.db.add(GroupMember(group_id=group.id, profile_id=self.other.id, role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE))
        await self.db.flush()
        member = await self.client.get(base_url, headers=self.other_headers)
        self.assertEqual(member.status_code, 200)
        self.assertIsNone(member.json()['group']['code'])
        self.assertEqual((await self.client.post(base_url+'/code/rotate', headers=self.other_headers)).status_code, 403)
        rotated = await self.client.post(base_url+'/code/rotate', headers=self.headers)
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotEqual(first.json()['group']['code'], rotated.json()['group']['code'])
