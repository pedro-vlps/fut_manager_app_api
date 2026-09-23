"""Testes transacionais do ciclo completo, sem persistir dados de teste."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from tests.test_auth import AuthTestCase
from src.models.entities import (EventPresence, GroupGuest, GroupMember, Match,
    PeladaEvent, PeladaGroup, Profile)
from src.models.enums import EventStatus, GroupRole, MembershipStatus, PresenceStatus
from src.routers.groups import router as groups_router
from src.routers.lifecycle import router as lifecycle_router


class LifecycleTests(AuthTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.include_router(groups_router)
        self.app.include_router(lifecycle_router)
        self.group = PeladaGroup(name='Ciclo teste', created_by_id=self.user.id)
        self.db.add(self.group)
        await self.db.flush()
        people = [self.user, self.other]
        for index in range(3):
            p = Profile(name=f'Jogador {index}', email=f'{uuid4()}@example.test', is_active=True)
            p.password = 'test-password-789'
            self.db.add(p)
            people.append(p)
        await self.db.flush()
        for person in people:
            self.db.add(GroupMember(group_id=self.group.id, profile_id=person.id,
                role=GroupRole.OWNER if person.id == self.user.id else GroupRole.MEMBER,
                status=MembershipStatus.ACTIVE))
        await self.db.flush()
        self.event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id,
            title='Ciclo teste', scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1),
            min_confirmed_players=6, max_confirmed_players=6, status=EventStatus.REGISTRATION_CLOSED)
        self.db.add(self.event)
        guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name='Convidado do ciclo')
        self.db.add(guest)
        await self.db.flush()
        self.presences = []
        for person in people:
            p = EventPresence(event_id=self.event.id, profile_id=person.id, status=PresenceStatus.CONFIRMED)
            self.db.add(p)
            self.presences.append(p)
        p = EventPresence(event_id=self.event.id, guest_id=guest.id, status=PresenceStatus.CONFIRMED)
        self.db.add(p)
        self.presences.append(p)
        await self.db.flush()
        token = (await self.login()).json()['access_token']
        self.headers = {'Authorization': f'Bearer {token}'}
        other_token = (await self.login(self.other, 'test-password-456')).json()['access_token']
        self.other_headers = {'Authorization': f'Bearer {other_token}'}
        self.base = f'/my-groups/{self.group.id}/events/{self.event.id}'

    async def post(self, suffix, body=None, status=200, headers=None):
        response = await self.client.post(self.base+suffix, json=body or {}, headers=headers or self.headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    async def build(self):
        return await self.post('/teams', {'mode':'manual', 'teams':[
            {'name':f'Time {i+1}', 'players':[{'presence_id':str(p.id), 'role':'goalkeeper' if j == 0 else 'player'}
                for j,p in enumerate(self.presences[i*2:i*2+2])]} for i in range(3)]})

    async def setup_match(self):
        state = await self.build()
        await self.post('/start')
        return await self.post('/kickoff', {'mode':'manual', 'team_ids':[t['id'] for t in state['teams'][:2]]})

    async def test_full_cycle_actions_queue_ties_and_rankings(self):
        state = await self.setup_match()
        first = state['current_match']
        first_id = first['id']
        team_a = state['teams'][0]
        team_b = state['teams'][1]
        team_c = state['teams'][2]
        action_url = f'/matches/{first_id}/actions'
        payload = {'id':str(uuid4()), 'team_id':team_a['id'], 'presence_id':team_a['players'][0]['presence_id'], 'action_type':'goal'}
        state = await self.post(action_url, payload)
        state = await self.post(action_url, payload)  # Mesmo ID não duplica gol.
        self.assertEqual(sum(s['goals'] for s in state['current_match']['scores']), 1)
        self.assertEqual(len(state['current_match']['actions']), 1)
        for action in ['assist','yellow_card','red_card']:
            state = await self.post(action_url, {**payload, 'id':str(uuid4()), 'action_type':action})
        own_id = str(uuid4())
        state = await self.post(action_url, {**payload, 'id':own_id, 'team_id':team_b['id'],
            'presence_id':team_b['players'][1]['presence_id'], 'action_type':'own_goal'})
        scores = {s['team_id']:s['goals'] for s in state['current_match']['scores']}
        self.assertEqual(scores, {team_a['id']:2, team_b['id']:0})
        remove_id = str(uuid4())
        await self.post(action_url, {**payload, 'id':remove_id})
        state = await self.post(f'{action_url}/{remove_id}/remove')
        self.assertEqual(sum(s['goals'] for s in state['current_match']['scores']), 2)
        await self.post(f'/matches/{first_id}/finish', {'advancing_team_id':team_b['id']}, status=422)
        state = await self.post(f'/matches/{first_id}/finish', {'advancing_team_id':team_a['id']})
        self.assertEqual(set(s['team_id'] for s in state['current_match']['scores']), {team_a['id'],team_c['id']})
        self.assertEqual(state['waiting_team_ids'], [team_b['id']])
        self.assertEqual(len(state['matches']), 2)
        self.assertEqual(state['current_match']['sequence'], 2)
        await self.post(f'/matches/{first_id}/finish', {'advancing_team_id':team_a['id']}, status=409)
        await self.post(action_url, {**payload,'id':str(uuid4())}, status=409)
        # Empate com avanço escolhido. Não vira vitória ou derrota nas estatísticas.
        second_id = state['current_match']['id']
        await self.post(f'/matches/{second_id}/finish', status=422)
        state = await self.post(f'/matches/{second_id}/finish', {'advancing_team_id':team_c['id']})
        self.assertEqual(set(s['team_id'] for s in state['current_match']['scores']), {team_c['id'],team_b['id']})
        self.assertEqual(state['waiting_team_ids'], [team_a['id']])
        second = next(m for m in state['matches'] if m['id'] == second_id)
        self.assertTrue(all(s['result'] == 'draw' for s in second['scores']))
        third = state['current_match']
        state = await self.post(f"/matches/{third['id']}/finish", {'random_tiebreak':True, 'continue_cycle':False})
        self.assertEqual(state['event']['status'], 'finished')
        self.assertIsNone(state['current_match'])
        self.assertEqual(state['waiting_team_ids'], [])
        self.assertIsNotNone(state['event']['finished_at'])
        self.assertIn(state['matches'][0]['advancing_team_id'], [team_b['id'],team_c['id']])
        await self.post('/start', status=409)
        ranking = (await self.client.get(f'/my-groups/{self.group.id}/rankings', headers=self.headers)).json()
        scorer = next(p for p in ranking if p['id'] == team_a['players'][0]['person_id'])
        self.assertEqual((scorer['goals'],scorer['assists'],scorer['yellow_cards'],scorer['red_cards'],scorer['wins']), (1,1,1,1,1))
        self.assertEqual(sum(p['own_goals'] for p in ranking), 1)
        self.assertTrue(any(p['is_guest'] for p in ranking))

    async def test_random_teams_random_kickoff_and_access(self):
        await self.post('/start', status=403, headers=self.other_headers)
        state = (await self.client.get(self.base+'/lifecycle', headers=self.other_headers)).json()
        self.assertFalse(state['can_manage'])
        await self.post('/start', status=409)
        await self.post('/teams', {'mode':'random','team_count':5}, status=422)
        await self.post('/kickoff', {'mode':'random'}, status=409)
        state = await self.post('/teams', {'mode':'random','team_count':3})
        self.assertEqual([len(t['players']) for t in state['teams']], [2,2,2])
        assigned = [p['presence_id'] for t in state['teams'] for p in t['players']]
        self.assertEqual(len(set(assigned)), 6)
        self.assertTrue(all(sum(p['role']=='goalkeeper' for p in t['players'])==1 for t in state['teams']))
        # A formação sorteada pode ser corrigida manualmente antes do início.
        selections = [{'name':t['name'], 'players':[{**p, 'role':'player'} for p in t['players']]} for t in state['teams']]
        selections[0]['players'][1], selections[1]['players'][1] = selections[1]['players'][1], selections[0]['players'][1]
        await self.post('/teams', {'mode':'manual','teams':selections}, status=403, headers=self.other_headers)
        state = await self.post('/teams', {'mode':'manual','teams':selections})
        self.assertEqual({p['presence_id'] for p in state['teams'][0]['players']},
            {p['presence_id'] for p in selections[0]['players']})
        state = await self.post('/start')
        self.assertEqual(state['event']['status'], 'in_progress')
        self.assertEqual((await self.post('/start'))['event']['started_at'], state['event']['started_at'])
        await self.post('/teams', {'mode':'random'}, status=409)
        await self.post('/teams', {'mode':'manual','teams':selections}, status=409)
        state = await self.post('/kickoff', {'mode':'random'})
        active = [s['team_id'] for s in state['current_match']['scores']]
        self.assertEqual(len(set(active)), 2)
        self.assertFalse(set(active).intersection(state['waiting_team_ids']))
        await self.post('/teams', {'mode':'random','team_count':3}, status=409)
        await self.post('/kickoff', {'mode':'random'}, status=409)
        await self.post('/finish', status=409)
        overview = (await self.client.get(f'/my-groups/{self.group.id}',headers=self.headers)).json()
        self.assertEqual(overview['next_event']['status'], 'in_progress')

    async def test_four_teams_admin_edit_and_changed_attendance(self):
        member = await self.db.scalar(select(GroupMember).where(GroupMember.group_id == self.group.id,
            GroupMember.profile_id == self.other.id))
        member.role = GroupRole.ADMIN
        await self.db.flush()
        state = await self.post('/teams', {'mode':'random','team_count':4}, headers=self.other_headers)
        self.assertEqual(len(state['teams']), 4)
        selections = [{'name':t['name'], 'players':[{**p, 'role':'player'} for p in t['players']]} for t in state['teams']]
        selections[0]['players'][0], selections[1]['players'][0] = selections[1]['players'][0], selections[0]['players'][0]
        await self.post('/teams', {'mode':'manual','teams':selections}, headers=self.other_headers)
        self.presences[0].status = PresenceStatus.CANCELLED
        self.event.min_confirmed_players = 3
        await self.db.flush()
        await self.post('/start', status=409)

    async def test_invalid_manual_rosters_and_action_scope(self):
        duplicate = str(self.presences[0].id)
        await self.post('/teams', {'mode':'manual','teams':[
            {'name':str(i),'players':[{'presence_id':duplicate}]} for i in range(3)]},status=422)
        state = await self.setup_match()
        current = state['current_match']
        waiting = state['teams'][2]
        body = {'id':str(uuid4()),'team_id':waiting['id'],'presence_id':waiting['players'][0]['presence_id'],'action_type':'goal'}
        await self.post(f"/matches/{current['id']}/actions",body,status=422)
        body.update(team_id=state['teams'][0]['id'],presence_id=str(uuid4()))
        await self.post(f"/matches/{current['id']}/actions",body,status=422)
        await self.post(f"/matches/{uuid4()}/finish",status=404)
        self.assertEqual((await self.client.get(self.base+'/lifecycle')).status_code,401)

    async def test_timer_manual_pause_resume_and_next_match_reset(self):
        state = await self.setup_match()
        match = state['current_match']
        path = f"/matches/{match['id']}/timer"
        self.assertEqual(match['timer_elapsed_ms'], 0)
        self.assertFalse(match['timer_running'])
        await self.post(path, {'action':'play'}, status=403, headers=self.other_headers)
        await self.post(path, {'action':'play'})
        row = await self.db.get(Match, match['id'])
        started = row.timer_running_since
        await self.post(path, {'action':'play'})
        self.assertEqual(row.timer_running_since, started)
        row.timer_running_since -= timedelta(seconds=65)
        await self.db.flush()
        state = await self.post(path, {'action':'pause'})
        paused = state['current_match']['timer_elapsed_ms']
        self.assertGreaterEqual(paused, 65000)
        self.assertFalse(state['current_match']['timer_running'])
        state = await self.post(path, {'action':'pause'})
        self.assertEqual(state['current_match']['timer_elapsed_ms'], paused)
        state = (await self.client.get(self.base+'/lifecycle', headers=self.headers)).json()
        self.assertEqual(state['current_match']['timer_elapsed_ms'], paused)
        await self.post(path, {'action':'play'})
        row.timer_running_since -= timedelta(seconds=10)
        await self.db.flush()
        state = await self.post(f"/matches/{match['id']}/finish", {'random_tiebreak':True})
        self.assertEqual(state['current_match']['timer_elapsed_ms'], 0)
        self.assertFalse(state['current_match']['timer_running'])
        previous = next(m for m in state['matches'] if m['id'] == match['id'])
        self.assertGreaterEqual(previous['timer_elapsed_ms'], paused + 10000)
        self.assertFalse(previous['timer_running'])
        await self.post(path, {'action':'play'}, status=409)
        current = state['current_match']['id']
        await self.post(f'/matches/{current}/finish', {'random_tiebreak':True, 'continue_cycle':False})
        await self.post(f'/matches/{current}/timer', {'action':'play'}, status=409)

    async def test_minimum_and_close_without_match(self):
        self.event.min_confirmed_players = 7
        self.event.max_confirmed_players = 8
        await self.db.flush()
        await self.post('/start',status=409)
        self.event.min_confirmed_players = 6
        await self.db.flush()
        await self.build()
        await self.post('/start')
        state = await self.post('/finish')
        self.assertEqual(state['event']['status'],'finished')
        await self.post('/teams',{'mode':'random'},status=409)

    async def test_finished_event_is_read_only_for_every_mutation(self):
        state = await self.setup_match()
        match = state['current_match']
        team = state['teams'][0]
        action = {'id':str(uuid4()),'team_id':team['id'],
            'presence_id':team['players'][0]['presence_id'],'action_type':'goal'}
        await self.post(f"/matches/{match['id']}/actions",action)
        state = await self.post(f"/matches/{match['id']}/finish",{'continue_cycle':False})
        self.assertFalse(state['can_manage'])
        snapshot = (await self.client.get(self.base+'/lifecycle',headers=self.headers)).json()
        self.assertFalse(snapshot['can_manage'])
        for path,body in [('/start',{}),('/teams',{'mode':'random'}),('/kickoff',{'mode':'random'}),
            ('/finish',{}),(f"/matches/{match['id']}/actions",{**action,'id':str(uuid4())}),
            (f"/matches/{match['id']}/actions/{action['id']}/remove",{}),
            (f"/matches/{match['id']}/finish",{'continue_cycle':False}),('/confirm',{})]:
            await self.post(path,body,status=409)
        # Mesmo chamando as rotas CRUD diretamente, não pode reabrir nem acrescentar dados.
        from fastapi import Depends
        from api_crud_generate_libary.routers.router import Router
        from src.models import CRUD_MODELS
        from src.routers.event_write_guard import event_write_guard
        for options in CRUD_MODELS:
            arguments = {key:value for key,value in options.items() if key not in {'prefix','tags'}}
            self.app.include_router(Router(**arguments).router,prefix=options['prefix'],
                dependencies=[Depends(event_write_guard(options['model_class']))])
        requests = [
            ('PATCH',f'/events/{self.event.id}',{'status':'registration_open'}),
            ('DELETE',f'/events/{self.event.id}',None),
            ('POST','/event-teams',{'event_id':str(self.event.id),'name':'Time invasor'}),
            ('POST','/matches',{'event_id':str(self.event.id),'sequence':99,'status':'in_progress'}),
            ('POST','/game-actions',{'match_id':match['id'],'team_id':team['id'],
                'player_id':str(self.user.id),'action_type':'goal'}),
            ('POST','/event-team-players',{'team_id':team['id'],'profile_id':str(self.user.id),'role':'player'}),
            ('POST','/event-presences',{'event_id':str(self.event.id),'profile_id':str(self.other.id),'status':'confirmed'}),
            ('DELETE',f'/groups/{self.group.id}',None),
        ]
        for method,path,body in requests:
            response = await self.client.request(method,path,json=body,headers=self.headers)
            self.assertEqual(response.status_code,409,response.text)
        self.assertEqual((await self.client.get(self.base+'/lifecycle',headers=self.headers)).json(),snapshot)
