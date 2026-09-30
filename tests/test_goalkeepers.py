"""Separate confirmation slots and the two-keeper rotation, using real PostgreSQL."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

from tests.test_auth import AuthTestCase
from src.models.entities import EventPresence, GroupGuest, GroupMember, PeladaEvent, PeladaGroup
from src.models.enums import EventStatus, GroupRole, MembershipStatus, PresenceStatus, TeamPlayerRole
from src.routers.groups import router as groups_router
from src.routers.lifecycle import router as lifecycle_router
from src.routers.scheduling import router as scheduling_router


class GoalkeeperTests(AuthTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        for router in (groups_router, lifecycle_router, scheduling_router):
            self.app.include_router(router)
        self.group = PeladaGroup(name='18 + 2', created_by_id=self.user.id)
        self.db.add(self.group)
        await self.db.flush()
        for person in (self.user, self.other):
            self.db.add(GroupMember(group_id=self.group.id, profile_id=person.id,
                role=GroupRole.OWNER if person == self.user else GroupRole.MEMBER,
                status=MembershipStatus.ACTIVE))
        self.event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id,
            title='18 jogadores e 2 goleiros', scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            min_confirmed_players=18, max_confirmed_players=18,
            min_confirmed_goalkeepers=2, max_confirmed_goalkeepers=2,
            status=EventStatus.REGISTRATION_OPEN)
        self.db.add(self.event)
        await self.db.flush()
        self.fields = [EventPresence(event_id=self.event.id, profile_id=self.user.id,
            role=TeamPlayerRole.PLAYER, status=PresenceStatus.CONFIRMED)]
        self.keepers = [EventPresence(event_id=self.event.id, profile_id=self.other.id,
            role=TeamPlayerRole.GOALKEEPER, status=PresenceStatus.CONFIRMED)]
        self.db.add_all(self.fields + self.keepers)
        await self.db.flush()
        for i in range(18):
            presence = await self.guest(TeamPlayerRole.PLAYER if i < 17 else TeamPlayerRole.GOALKEEPER)
            (self.fields if i < 17 else self.keepers).append(presence)
        self.headers = {'Authorization': 'Bearer ' + (await self.login()).json()['access_token']}
        self.other_headers = {'Authorization': 'Bearer ' + (await self.login(self.other, 'test-password-456')).json()['access_token']}
        self.base = f'/my-groups/{self.group.id}/events/{self.event.id}'

    async def guest(self, role):
        guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name=f'Convidado {uuid4()}')
        self.db.add(guest)
        await self.db.flush()
        presence = EventPresence(event_id=self.event.id, guest_id=guest.id, role=role, status=PresenceStatus.CONFIRMED)
        self.db.add(presence)
        await self.db.flush()
        await self.db.refresh(presence)
        return presence

    async def post(self, suffix, body=None, status=200, headers=None):
        response = await self.client.post(self.base + suffix, json=body or {}, headers=headers or self.headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    async def state(self):
        response = await self.client.get(self.base + '/lifecycle', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_eighteen_plus_two_draw_rotation_history_and_rankings(self):
        state = await self.post('/teams', {'mode': 'random', 'team_count': 3})
        self.assertEqual([sum(p['role'] == 'player' for p in t['players']) for t in state['teams']], [6, 6, 6])
        self.assertEqual(sorted(sum(p['role'] == 'goalkeeper' for p in t['players']) for t in state['teams']), [0, 1, 1])
        await self.post('/start')
        # Include the team originally drawn without a keeper in the first game.
        selected = [state['teams'][1]['id'], state['teams'][2]['id']]
        state = await self.post('/kickoff', {'mode': 'manual', 'team_ids': selected})
        first = state['current_match']
        for team in selected:
            lineup = [p for p in first['players'] if p['team_id'] == team]
            self.assertEqual(len(lineup), 7)
            self.assertEqual(sum(p['role'] == 'goalkeeper' for p in lineup), 1)
        keeper_ids = {str(p.id) for p in self.keepers}
        self.assertEqual({p['presence_id'] for p in first['players'] if p['role'] == 'goalkeeper'}, keeper_ids)
        original_lineup = first['players']
        for _ in range(5):
            match = state['current_match']
            winner, loser = [s['team_id'] for s in match['scores']]
            challenger = state['waiting_team_ids'][0]
            old_keepers = {p['team_id']: p['presence_id'] for p in match['players'] if p['role'] == 'goalkeeper'}
            scorer = next(p for p in match['players'] if p['team_id'] == winner and p['role'] == 'player')
            await self.post(f"/matches/{match['id']}/actions", {'id': str(uuid4()), 'team_id': winner,
                'presence_id': scorer['presence_id'], 'action_type': 'goal'})
            state = await self.post(f"/matches/{match['id']}/finish")
            new_keepers = {p['team_id']: p['presence_id'] for p in state['current_match']['players'] if p['role'] == 'goalkeeper'}
            self.assertEqual(new_keepers, {winner: old_keepers[winner], challenger: old_keepers[loser]})
            self.assertEqual(len(state['current_match']['players']), 14)
            self.assertFalse(any(p['role'] == 'goalkeeper' for t in state['teams'] if t['id'] in state['waiting_team_ids'] for p in t['players']))
        historical = next(m for m in state['matches'] if m['id'] == first['id'])
        self.assertEqual(historical['players'], original_lineup)
        rankings = (await self.client.get(f'/my-groups/{self.group.id}/rankings', headers=self.headers)).json()
        keepers = [p for p in rankings if p['goalkeeper_matches']]
        self.assertEqual(sorted(p['goalkeeper_matches'] for p in keepers), [5, 5])
        self.assertEqual(sum(p['goals_conceded'] for p in keepers), 5)

    async def test_four_teams_and_tied_games_keep_both_keepers(self):
        state = await self.post('/teams', {'mode': 'random', 'team_count': 4})
        self.assertEqual([sum(p['role'] == 'player' for p in t['players']) for t in state['teams']], [5, 5, 4, 4])
        await self.post('/start')
        state = await self.post('/kickoff', {'mode': 'random'})
        for i in range(4):
            match = state['current_match']
            self.assertEqual(sum(p['role'] == 'goalkeeper' for p in match['players']), 2)
            self.assertEqual(len(state['waiting_team_ids']), 2)
            state = await self.post(f"/matches/{match['id']}/finish", {'random_tiebreak': True})

    async def test_capacity_role_change_waitlist_promotion_and_counts(self):
        waiting_field = await self.guest(TeamPlayerRole.PLAYER)
        waiting_keeper = await self.guest(TeamPlayerRole.GOALKEEPER)
        self.assertEqual(waiting_field.status, PresenceStatus.WAITLIST)
        self.assertEqual(waiting_keeper.status, PresenceStatus.WAITLIST)
        changed = await self.post('/confirm', {'role': 'goalkeeper'})
        self.assertEqual(changed['status'], 'waitlist')
        self.assertEqual(changed['role'], 'goalkeeper')
        await self.db.refresh(waiting_field)
        self.assertEqual(waiting_field.status, PresenceStatus.CONFIRMED)
        self.keepers[0].status = PresenceStatus.CANCELLED
        await self.db.flush()
        await self.db.refresh(self.fields[0])
        await self.db.refresh(waiting_keeper)
        self.assertEqual(self.fields[0].status, PresenceStatus.CONFIRMED)
        self.assertEqual(waiting_keeper.status, PresenceStatus.WAITLIST)
        overview = (await self.client.get(f'/my-groups/{self.group.id}', headers=self.headers)).json()['next_event']
        self.assertEqual((overview['confirmed_count'], overview['confirmed_players_count'], overview['confirmed_goalkeepers_count']), (20, 18, 2))
        people = (await self.client.get(self.base + '/confirmed', headers=self.headers)).json()
        self.assertEqual(sum(p['role'] == 'goalkeeper' for p in people), 2)
        self.assertEqual((await self.post('/confirm', {'role': 'goalkeeper'}))['id'], changed['id'])

    async def test_minimums_manual_roles_settings_permissions_and_locks(self):
        settings = dict(min_confirmed_players=18, max_confirmed_players=18,
            min_confirmed_goalkeepers=2, max_confirmed_goalkeepers=2)
        await self.post('/confirmation-settings', settings, status=403, headers=self.other_headers)
        await self.post('/confirmation-settings', {**settings, 'max_confirmed_goalkeepers': 1}, status=422)
        state = await self.post('/teams', {'mode': 'random', 'team_count': 3})
        manual = [{'name': t['name'], 'players': t['players']} for t in state['teams']]
        next(p for t in manual for p in t['players'] if p['role'] == 'goalkeeper')['role'] = 'player'
        await self.post('/teams', {'mode': 'manual', 'teams': manual}, status=422)
        # Total attendance remains sufficient; the keeper minimum must still fail.
        self.keepers[0].status = PresenceStatus.CANCELLED
        await self.db.flush()
        await self.post('/start', status=409)
        self.keepers[0].status = PresenceStatus.CONFIRMED
        await self.db.flush()
        state = await self.post('/confirmation-settings', settings)
        self.assertEqual(state['teams'], [])
        await self.post('/teams', {'mode': 'random', 'team_count': 3})
        await self.post('/start')
        await self.post('/confirmation-settings', settings, status=409)
        await self.post('/confirm', {'role': 'goalkeeper'}, status=409)

    async def test_three_keepers_stay_with_their_teams_and_manual_draw(self):
        self.event.max_confirmed_goalkeepers = 3
        await self.db.flush()
        await self.guest(TeamPlayerRole.GOALKEEPER)
        state = await self.post('/teams', {'mode': 'random', 'team_count': 3})
        manual = [{'name': t['name'], 'players': t['players']} for t in state['teams']]
        state = await self.post('/teams', {'mode': 'manual', 'teams': manual})
        originals = {t['id']: next(p['presence_id'] for p in t['players'] if p['role'] == 'goalkeeper') for t in state['teams']}
        await self.post('/start')
        state = await self.post('/kickoff', {'mode': 'random'})
        state = await self.post(f"/matches/{state['current_match']['id']}/finish", {'random_tiebreak': True})
        for player in state['current_match']['players']:
            if player['role'] == 'goalkeeper':
                self.assertEqual(player['presence_id'], originals[player['team_id']])

    async def test_schedule_and_recurrence_preserve_separate_slots(self):
        url = f'/my-groups/{self.group.id}/schedule'
        body = dict(id=str(uuid4()), title='Semanal 18+2', scheduled_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            min_confirmed_players=18, max_confirmed_players=18, min_confirmed_goalkeepers=2,
            max_confirmed_goalkeepers=2, recurring_weekly=True)
        response = await self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['min_confirmed_goalkeepers'], 2)
        retry = await self.client.post(url, json={**body, 'max_confirmed_goalkeepers': 3}, headers=self.headers)
        self.assertEqual(retry.status_code, 409)
        self.event.recurring_weekly = True
        await self.db.flush()
        await self.post('/teams', {'mode': 'random', 'team_count': 3})
        await self.post('/start')
        await self.post('/finish')
        successor = await self.db.scalar(select(PeladaEvent).where(PeladaEvent.recurrence_parent_id == self.event.id))
        self.assertEqual((successor.min_confirmed_players, successor.max_confirmed_players,
                          successor.min_confirmed_goalkeepers, successor.max_confirmed_goalkeepers), (18, 18, 2, 2))

    async def test_migration_is_repeatable_and_sql_capacity_is_role_specific(self):
        raw = await self.connection.get_raw_connection()
        migration = Path('src/databases/scripts/migrations/014_goalkeeper_confirmations.sql').read_text()
        await raw.driver_connection.execute(migration)
        await raw.driver_connection.execute(migration)
        await self.db.execute(text('UPDATE pelada_events SET min_confirmed_players=17, max_confirmed_players=17 WHERE id=:id'), {'id': self.event.id})
        state = await self.state()
        self.assertEqual(sum(p['role'] == 'player' for p in state['participants']), 17)
        self.assertEqual(sum(p['role'] == 'goalkeeper' for p in state['participants']), 2)
