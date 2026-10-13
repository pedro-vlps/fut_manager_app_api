import unittest
from uuid import uuid4
from tests import test_lifecycle as lifecycle_tests
from tests import test_feedback as championship_tests


class ChampionshipCardsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = championship_tests.FeedbackIntegrationTests.asyncSetUp
    asyncTearDown = championship_tests.FeedbackIntegrationTests.asyncTearDown
    login = championship_tests.FeedbackIntegrationTests.login
    setup_api = championship_tests.FeedbackIntegrationTests.setup_api
    create_cup = championship_tests.FeedbackIntegrationTests.create_cup
    create_ready_club = championship_tests.FeedbackIntegrationTests.create_ready_club
    fill_cup = championship_tests.FeedbackIntegrationTests.fill_cup
    start_cup = championship_tests.FeedbackIntegrationTests.start_cup
    post_score = championship_tests.FeedbackIntegrationTests.post_score

    async def test_second_yellow_retry_removal_rankings_and_next_match(self):
        data = await self.start_cup()
        match = data['matches'][0]
        player = next(e['players'][0]['id'] for e in data['entries'] if e['club_id'] == match['home_id'])
        url = self.base + f"/matches/{match['id']}/actions"
        body = dict(id=str(uuid4()), presence_id=player, team_id=match['home_id'], action_type='yellow_card')
        async def add(payload, status=200):
            response = await self.client.post(url, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, status, response.text)
            return response.json()
        data = await add(body)
        self.assertEqual(len(data['matches'][0]['actions']), 1)
        second = {**body, 'id': str(uuid4())}
        data = await add(second)
        data = await add(second)  # Retry não duplica amarelo nem vermelho.
        actions = data['matches'][0]['actions']
        self.assertEqual([a['action_type'] for a in actions], ['yellow_card', 'yellow_card', 'red_card'])
        red = actions[-1]
        self.assertTrue(red['auto_generated'])
        for kind in ('yellow_card', 'red_card'):
            await add({**body, 'id': str(uuid4()), 'action_type': kind}, 409)
        response = await self.client.post(url+f"/{red['id']}/remove", headers=self.headers)
        self.assertEqual(response.status_code, 409)
        response = await self.client.post(url+f"/{body['id']}/remove", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['matches'][0]['actions']), 1)
        data = await add({**body, 'id': str(uuid4())})
        self.assertEqual(data['matches'][0]['actions'][-1]['id'], red['id'])
        data = await self.post_score(data['matches'][0], home_score=0, away_score=0, winner_id=match['home_id'],
            action_ids=[a['id'] for a in data['matches'][0]['actions']])
        row = next(p for p in data['player_rankings'] if p['profile_id'] == player)
        self.assertEqual((row['yellow_cards'], row['red_cards']), (2, 1))
        data = await self.post_score(data['matches'][1], home_score=0, away_score=0, winner_id=data['matches'][1]['home_id'])
        final = data['matches'][-1]
        response = await self.client.post(self.base+f"/matches/{final['id']}/actions", headers=self.headers,
            json={**body, 'id': str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['matches'][-1]['actions']), 1)

    async def test_direct_red_is_preserved_when_yellow_is_removed(self):
        data = await self.start_cup('league')
        match = data['matches'][0]
        player = next(e['players'][0]['id'] for e in data['entries'] if e['club_id'] == match['home_id'])
        url = self.base + f"/matches/{match['id']}/actions"
        yellow = dict(id=str(uuid4()), presence_id=player, team_id=match['home_id'], action_type='yellow_card')
        for payload in (yellow, {**yellow, 'id': str(uuid4()), 'action_type': 'red_card'}):
            response = await self.client.post(url, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
        response = await self.client.post(url+f"/{yellow['id']}/remove", headers=self.headers)
        actions = response.json()['matches'][0]['actions']
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action_type'], 'red_card')
        self.assertFalse(actions[0]['auto_generated'])


class PeladaCardsTests(lifecycle_tests.LifecycleFixture):
    async def check_person(self, guest=False):
        if guest:
            state = await self.build()
            await self.post('/start')
            state = await self.post('/kickoff', {'mode': 'manual', 'team_ids': [state['teams'][0]['id'], state['teams'][2]['id']]})
        else:
            state = await self.setup_match()
        match = state['current_match']
        player = next(p for p in match['players'] if p['is_guest'] == guest)
        url = f"/matches/{match['id']}/actions"
        yellow = dict(id=str(uuid4()), presence_id=player['presence_id'], team_id=player['team_id'], action_type='yellow_card')
        state = await self.post(url, yellow)
        self.assertEqual(len(state['current_match']['actions']), 1)
        second = {**yellow, 'id': str(uuid4())}
        state = await self.post(url, second)
        state = await self.post(url, second)
        actions = state['current_match']['actions']
        self.assertEqual(len(actions), 3)
        red = next(a for a in actions if a['action_type'] == 'red_card')
        self.assertTrue(red['auto_generated'])
        self.assertEqual(red['person_id'], player['person_id'])
        await self.post(url+f"/{red['id']}/remove", status=409)
        await self.post(url, {**yellow, 'id': str(uuid4())}, status=409)
        state = await self.post(url+f"/{yellow['id']}/remove")
        self.assertEqual(len(state['current_match']['actions']), 1)
        state = await self.post(url, {**yellow, 'id': str(uuid4())})
        self.assertEqual(next(a['id'] for a in state['current_match']['actions'] if a['auto_generated']), red['id'])
        await self.post(f"/matches/{match['id']}/finish", {'advancing_team_id': player['team_id'], 'continue_cycle': False})
        response = await self.client.get(f'/my-groups/{self.group.id}/events/{self.event.id}/rankings', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        row = next(p for p in response.json() if p['id'] == player['person_id'])
        self.assertEqual((row['yellow_cards'], row['red_cards']), (2, 1))

    async def test_second_yellow_for_registered_player(self):
        await self.check_person()

    async def test_second_yellow_for_guest(self):
        await self.check_person(guest=True)
