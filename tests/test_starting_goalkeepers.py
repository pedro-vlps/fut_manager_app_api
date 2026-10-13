import unittest
import re
from pathlib import Path
from uuid import UUID, uuid4
from src.models.entities import Profile
from tests import test_championships as base


class StartingGoalkeeperTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.ChampionshipTests.asyncSetUp
    asyncTearDown = base.ChampionshipTests.asyncTearDown
    login = base.ChampionshipTests.login
    setup_api = base.ChampionshipTests.setup_api
    create_cup = base.ChampionshipTests.create_cup
    create_ready_club = base.ChampionshipTests.create_ready_club
    fill_cup = base.ChampionshipTests.fill_cup

    async def send(self, url, payload=None, headers=None, status=200):
        response = await self.client.post(url, json=payload or {}, headers=headers or self.headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    async def two_teams(self):
        await self.setup_api()
        clubs = []
        for owner, headers in ((self.user, self.headers), (self.other, self.other_headers)):
            club = await self.create_ready_club(owner, owner.name)
            view = (await self.client.get('/clubs', headers=headers)).json()
            team = next(c for c in view if c['id'] == str(club.id))
            keeper = next(p['id'] for p in team['members'] if p['id'] != str(owner.id))
            await self.send(f'/clubs/{club.id}/goalkeeper', {'goalkeeper_id': keeper}, headers)
            clubs.append((club, keeper, headers))
        cup = await self.create_cup(2, 'league')
        self.base = f"/championships/{cup['id']}"
        for club, _, headers in clubs:
            await self.send(self.base+'/entries', {'club_id': str(club.id)}, headers)
        data = await self.send(self.base+'/start')
        self.match = data['matches'][0]
        self.match_url = self.base + f"/matches/{self.match['id']}"
        self.clubs = clubs
        return data

    async def goal(self, team, player, kind='goal'):
        return await self.send(self.match_url+'/actions', dict(id=str(uuid4()), team_id=team,
            presence_id=player, action_type=kind))

    async def finish(self, data):
        match = data['matches'][0]
        actions = match['actions']
        home_score = sum(a['action_type'] == 'goal' and a['team_id'] == match['home_id'] or a['action_type'] == 'own_goal' and a['team_id'] == match['away_id'] for a in actions)
        away_score = sum(a['action_type'] == 'goal' and a['team_id'] == match['away_id'] or a['action_type'] == 'own_goal' and a['team_id'] == match['home_id'] for a in actions)
        return await self.send(self.match_url+'/score', dict(home_score=home_score, away_score=away_score,
            action_ids=[a['id'] for a in actions]))

    async def test_roster_snapshot_defaults_permissions_and_pending_updates(self):
        data = await self.two_teams()
        for club, keeper, _ in self.clubs:
            entry = next(e for e in data['entries'] if e['club_id'] == str(club.id))
            self.assertEqual(entry['starting_goalkeeper_id'], keeper)
            side = 'home' if data['matches'][0]['home_id'] == str(club.id) else 'away'
            self.assertEqual(data['matches'][0][side+'_goalkeeper_id'], keeper)
        home = self.clubs[0][0]
        await self.send(f'/clubs/{home.id}/goalkeeper', {'goalkeeper_id': str(uuid4())}, status=422)
        await self.send(f'/clubs/{home.id}/goalkeeper', {'goalkeeper_id': self.clubs[0][1]}, self.other_headers, 403)
        data = await self.send(self.base+f'/clubs/{home.id}/goalkeeper', {'goalkeeper_id': str(self.user.id)})
        self.assertEqual(data['matches'][0]['home_goalkeeper_id'], str(self.user.id))
        self.assertIsNone(data['matches'][0]['started_at'])

    async def test_substitution_assigns_each_goal_and_own_goal_to_active_keeper(self):
        data = await self.two_teams()
        old = self.clubs[1][1]
        data = await self.send(self.match_url+'/kickoff')
        data = await self.goal(self.match['home_id'], str(self.user.id))
        await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': str(self.other.id)}, self.other_headers, 403)
        # O time define o próximo titular sem modificar o goleiro do jogo em curso.
        data = await self.send(self.base+f"/clubs/{self.clubs[1][0].id}/goalkeeper", {'goalkeeper_id': str(self.other.id)}, self.other_headers)
        self.assertEqual(data['matches'][0]['away_goalkeeper_id'], old)
        data = await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': str(self.other.id)})
        data = await self.goal(self.match['away_id'], str(self.other.id), 'own_goal')
        self.assertEqual([a['goalkeeper_id'] for a in data['matches'][0]['actions']], [old, str(self.other.id)])
        data = await self.finish(data)
        ranks = {p['profile_id']: p for p in data['player_rankings']}
        for keeper in (old, str(self.other.id)):
            self.assertEqual((ranks[keeper]['goalkeeper_matches'], ranks[keeper]['goals_conceded']), (1, 1))

    async def test_removing_goal_keeps_other_goals_with_their_original_keeper(self):
        data = await self.two_teams()
        old = self.clubs[1][1]
        data = await self.goal(self.match['home_id'], str(self.user.id))
        removed = data['matches'][0]['actions'][0]['id']
        await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': str(self.other.id)})
        data = await self.goal(self.match['home_id'], str(self.user.id))
        data = await self.send(self.match_url+f'/actions/{removed}/remove')
        data = await self.finish(data)
        ranks = {p['profile_id']: p for p in data['player_rankings']}
        self.assertEqual(ranks[old]['goals_conceded'], 0)
        self.assertEqual(ranks[str(self.other.id)]['goals_conceded'], 1)
        self.assertEqual(ranks[old]['goalkeeper_matches'], 1)

    async def test_return_to_goal_counts_one_appearance_and_blocks_ambiguous_bulk_score(self):
        data = await self.two_teams()
        old = self.clubs[1][1]
        await self.send(self.match_url+'/kickoff')
        await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': str(self.other.id)})
        data = await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': old})
        await self.send(self.match_url+'/goalkeepers', {'away_goalkeeper_id': None}, status=422)
        await self.send(self.match_url+'/score', {'home_score': 1, 'away_score': 0}, status=422)
        data = await self.finish(data)
        ranks = {p['profile_id']: p for p in data['player_rankings']}
        self.assertEqual((ranks[old]['goalkeeper_matches'], ranks[str(self.other.id)]['goalkeeper_matches']), (1, 1))

    async def test_walkover_accepts_automatic_defaults_without_keeper_statistics(self):
        data = await self.two_teams()
        data = await self.send(self.match_url+'/score', {'home_score': 3, 'away_score': 0,
            'winner_id': self.match['home_id'], 'walkover': True})
        self.assertTrue(all(p['goalkeeper_matches'] == p['goals_conceded'] == 0 for p in data['player_rankings']))
        self.assertEqual(data['matches'][0]['goalkeeper_history'], [])

    async def test_manual_match_choice_and_migration_reexecution_are_preserved(self):
        data = await self.two_teams()
        data = await self.send(self.match_url+'/goalkeepers', {'home_goalkeeper_id': str(self.user.id)})
        await self.send(f'/clubs/{self.clubs[0][0].id}/goalkeeper', {'goalkeeper_id': None})
        data = (await self.client.get(self.base, headers=self.headers)).json()
        self.assertEqual(data['matches'][0]['home_goalkeeper_id'], str(self.user.id))
        self.assertTrue(data['matches'][0]['home_goalkeeper_override'])
        self.assertFalse(data['matches'][0]['away_goalkeeper_override'])
        sql = Path('src/databases/scripts/migrations/027_starting_goalkeepers.sql').read_text(encoding='utf-8')
        raw = await self.connection.get_raw_connection()
        await raw.driver_connection.execute(re.sub(r'(?m)^(BEGIN|COMMIT);\s*$', '', sql))
        stored = await raw.driver_connection.fetchrow('SELECT home_goalkeeper_override, away_goalkeeper_override FROM championship_matches WHERE id=$1', UUID(self.match['id']))
        self.assertTrue(stored['home_goalkeeper_override'])
        self.assertFalse(stored['away_goalkeeper_override'])
        data = (await self.client.get(self.base, headers=self.headers)).json()
        self.assertEqual(data['matches'][0]['home_goalkeeper_id'], str(self.user.id))
        self.assertFalse(data['matches'][0]['away_goalkeeper_override'])

    async def test_next_knockout_round_inherits_default_and_groups_can_be_redrawn(self):
        await self.setup_api()
        for format in ('knockout', 'groups_knockout'):
            cup = await self.create_cup(4, format)
            await self.fill_cup(cup)
            url = f"/championships/{cup['id']}"
            data = (await self.client.get(url, headers=self.headers)).json()
            keepers = {}
            for entry in data['entries']:
                owner = await self.db.get(Profile, UUID(entry['owner_id']))
                headers = {'Authorization': 'Bearer '+(await self.login(owner)).json()['access_token']}
                keeper = entry['players'][0]['id']
                await self.send(url+f"/clubs/{entry['club_id']}/goalkeeper", {'goalkeeper_id': keeper}, headers)
                keepers[entry['club_id']] = keeper
            data = await self.send(url+'/start')
            if format == 'groups_knockout':
                data = await self.send(url+'/groups', {'groups': [[e['club_id'] for e in data['entries']]]})
                self.assertTrue(all(m['home_goalkeeper_id'] == keepers[m['home_id']] for m in data['matches']))
            else:
                for match in list(data['matches']):
                    data = await self.send(url+f"/matches/{match['id']}/score", {'home_score': 0, 'away_score': 0, 'winner_id': match['home_id']})
                final = data['matches'][-1]
                self.assertEqual((final['home_goalkeeper_id'], final['away_goalkeeper_id']), (keepers[final['home_id']], keepers[final['away_id']]))
