import unittest
from itertools import product
from types import SimpleNamespace
from uuid import UUID, uuid4
from src.models.championships import Championship
from src.helpers.championships import cascade_next, initial_fixtures, loser
from src.helpers.championship_trophies import trophy_winners
from src.schemas.championships import PlayerRanking
from src.routers.trophies import router as trophies_router
from src.services.championships import ChampionshipsService
from src.controllers.championships import award_championship
from tests import test_championships as base_tests


class CascadeBracketTests(unittest.TestCase):
    def test_every_outcome_preserves_seeding_elimination_and_winner_rest(self):
        entries = [SimpleNamespace(club_id=i, seed=i + 1) for i in range(4)]
        for outcomes in product([0, 1], repeat=6):
            matches = []
            fixtures = initial_fixtures(entries, 'cascade')
            losses = {i: 0 for i in range(4)}
            while fixtures:
                for stage, round, pool, home, away in fixtures:
                    self.assertLess(losses[home], 2)
                    self.assertLess(losses[away], 2)
                    m = SimpleNamespace(stage=stage, round=round, pool=pool, home_id=home, away_id=away,
                        home_score=1, winner_id=(home, away)[outcomes[len(matches)]])
                    losses[loser(m)] += 1
                    matches.append(m)
                fixtures = cascade_next(matches)
            self.assertEqual(len(matches), 6)
            self.assertEqual((matches[0].home_id, matches[0].away_id), (0, 3))
            self.assertEqual((matches[1].home_id, matches[1].away_id), (1, 2))
            finalist = loser(matches[2])
            self.assertNotIn(finalist, (matches[3].home_id, matches[3].away_id))
            self.assertIn(finalist, (matches[4].home_id, matches[4].away_id))
            self.assertEqual(matches[5].home_id, matches[2].winner_id)
            self.assertEqual(matches[5].away_id, matches[4].winner_id)

    def test_tied_positive_individual_rankings_and_incomplete_stats(self):
        club, other = uuid4(), uuid4()
        rows = [PlayerRanking(profile_id=uuid4(), club_id=club, name='A', goals=2, assists=1),
                PlayerRanking(profile_id=uuid4(), club_id=other, name='B', goals=2, assists=1)]
        awards = list(trophy_winners(rows, club, other, True))
        self.assertEqual(len(awards), 6)
        self.assertEqual(len(list(trophy_winners(rows, club, other, False))), 2)
        for row in rows:
            row.goals = row.assists = 0
        self.assertEqual(len(list(trophy_winners(rows, club, other, True))), 2)


class CascadeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base_tests.ChampionshipTests.asyncSetUp
    asyncTearDown = base_tests.ChampionshipTests.asyncTearDown
    login = base_tests.ChampionshipTests.login
    setup_api = base_tests.ChampionshipTests.setup_api
    create_cup = base_tests.ChampionshipTests.create_cup
    create_ready_club = base_tests.ChampionshipTests.create_ready_club
    fill_cup = base_tests.ChampionshipTests.fill_cup

    async def test_six_games_order_statistics_and_persistent_profile_trophies(self):
        await self.setup_api()
        self.app.include_router(trophies_router)
        cup = await self.create_cup(format='cascade')
        await self.fill_cup(cup)
        base = f"/championships/{cup['id']}"
        data = (await self.client.post(base + '/start', headers=self.headers)).json()
        second = data['matches'][1]
        self.assertEqual((await self.client.post(base + f"/matches/{second['id']}/score", headers=self.headers,
            json={'home_score': 0, 'away_score': 0, 'winner_id': second['home_id']})).status_code, 409)
        for game in range(6):
            match = next(m for m in data['matches'] if m['home_score'] is None)
            home = next(e for e in data['entries'] if e['club_id'] == match['home_id'])['players'][0]['id']
            away = next(e for e in data['entries'] if e['club_id'] == match['away_id'])['players'][0]['id']
            url = base + f"/matches/{match['id']}/score"
            # O finalista da chave dos perdedores ganha a final única.
            stats = [{'profile_id': away if game == 5 else home, 'goals': 1}]
            scoring_club = match['away_id'] if game == 5 else match['home_id']
            assistant = next(e for e in data['entries'] if e['club_id'] == scoring_club)['players'][1]['id']
            stats.append({'profile_id': assistant, 'assists': 1})
            payload = {'home_score': 0 if game == 5 else 1, 'away_score': 1 if game == 5 else 0, 'statistics': stats}
            self.assertEqual((await self.client.post(url, headers=self.other_headers, json=payload)).status_code, 403)
            if game == 0:
                for invalid in [[], [{'profile_id': str(uuid4()), 'goals': 1}], stats + stats,
                                [{'profile_id': home, 'goals': 1, 'assists': 1}]]:
                    response = await self.client.post(url, headers=self.headers, json={**payload, 'statistics': invalid})
                    self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual((await self.client.post(url, headers=self.headers,
                    json={'home_score': 0, 'away_score': 0, 'statistics': []})).status_code, 422)
            response = await self.client.post(url, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual((await self.client.post(url, headers=self.headers, json=payload)).status_code, 409)
        self.assertEqual(data['status'], 'finished')
        self.assertEqual(data['champion_id'], data['matches'][-1]['away_id'])
        self.assertTrue(data['statistics_complete'])
        self.assertEqual(sum(p['goals'] for p in data['player_rankings']), 6)
        self.assertEqual(sum(p['assists'] for p in data['player_rankings']), 6)
        self.assertEqual({t['category'] for t in data['trophies']},
            {'championship_champion', 'championship_runner_up', 'championship_goals', 'championship_assists'})
        service = ChampionshipsService(self.db)
        # Reprocessar a premiação não duplica registros.
        await award_championship(service, await service.get(Championship, UUID(cup['id'])), (await service.matches(UUID(cup['id'])))[-1])
        reread = (await self.client.get(base, headers=self.headers)).json()
        self.assertEqual(len(data['trophies']), len(reread['trophies']))
        from src.models.entities import Profile
        player = await self.db.get(Profile, UUID(data['trophies'][0]['profile_id']))
        headers = {'Authorization': 'Bearer ' + (await self.login(player)).json()['access_token']}
        collection = (await self.client.get('/auth/me/trophies', headers=headers)).json()
        self.assertGreater(collection['total'], 0)
        self.assertTrue(all(t['championship_id'] == cup['id'] and t['season_id'] is None for t in collection['trophies']))
        self.assertEqual((await self.client.get('/auth/me/trophies', headers=self.other_headers)).json()['total'], 0)

    async def test_cascade_capacity_rejected_and_other_formats_unchanged(self):
        await self.setup_api()
        for capacity in [8, 16]:
            response = await self.client.post('/championships', headers=self.headers,
                json={'name': 'Cascata', 'season': '2026', 'format': 'cascade', 'capacity': capacity})
            self.assertEqual(response.status_code, 422)
            self.assertEqual((await self.create_cup(capacity, 'knockout'))['capacity'], capacity)
