from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from tests.test_auth import AuthTestCase
from src.models.entities import (EventPresence, EventTeam, GameAction, GroupGuest,
    GroupMember, Match, MatchLineup, MatchTeam, PeladaEvent, PeladaGroup)
from src.models.enums import (EventStatus, GameActionType, GroupRole, MembershipStatus,
    MatchResult, MatchStatus, PresenceStatus, TeamPlayerRole)
from src.routers.groups import router as groups_router


class GroupIntegrationTests(AuthTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.include_router(groups_router)
        self.group = PeladaGroup(name='Grupo teste', created_by_id=self.user.id)
        self.db.add(self.group)
        await self.db.flush()
        self.db.add(GroupMember(group_id=self.group.id, profile_id=self.user.id,
            role=GroupRole.OWNER, status=MembershipStatus.ACTIVE))
        await self.db.flush()
        token = (await self.login()).json()['access_token']
        self.headers = {'Authorization': f'Bearer {token}'}
        self.base = f'/my-groups/{self.group.id}'

    async def event(self, days=1, status=EventStatus.REGISTRATION_OPEN, **kwargs):
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id,
            title='Pelada teste', scheduled_at=datetime.now(timezone.utc) + timedelta(days=days),
            min_confirmed_players=1, max_confirmed_players=1, status=status, **kwargs)
        self.db.add(event)
        await self.db.flush()
        return event

    async def test_next_event_history_and_authorization(self):
        past = await self.event(days=-1, status=EventStatus.FINISHED)
        await self.event(days=0.1, status=EventStatus.CANCELLED)
        await self.event(days=0.2, status=EventStatus.DRAFT)
        upcoming = await self.event(days=1)
        await self.event(days=2)
        expired_open = await self.event(days=-2)
        result = await self.client.get(self.base, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['next_event']['id'], str(expired_open.id))
        history = (await self.client.get(f'{self.base}/history', headers=self.headers)).json()
        self.assertIn(str(past.id), [event['id'] for event in history])
        self.assertNotIn(str(upcoming.id), [event['id'] for event in history])
        self.assertNotIn(str(expired_open.id), [event['id'] for event in history])
        self.assertEqual(len((await self.client.get(f'{self.base}/members', headers=self.headers)).json()), 1)
        outsider = (await self.login(self.other, 'test-password-456')).json()['access_token']
        for suffix in ['', '/history', '/members', '/rankings', '/standings', f'/events/{upcoming.id}/confirmed']:
            response = await self.client.get(self.base + suffix, headers={'Authorization': f'Bearer {outsider}'})
            self.assertEqual(response.status_code, 404)
        response = await self.client.post(f'{self.base}/events/{upcoming.id}/confirm', headers={'Authorization': f'Bearer {outsider}'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual((await self.client.get(self.base)).status_code, 401)
        self.assertEqual((await self.client.get(f'{self.base}/events/{uuid4()}/confirmed', headers=self.headers)).status_code, 404)

    async def test_confirmation_idempotency_capacity_and_guest_names(self):
        event = await self.event()
        url = f'{self.base}/events/{event.id}/confirm'
        first = await self.client.post(url, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['status'], 'confirmed')
        again = await self.client.post(url, headers=self.headers)
        self.assertEqual(again.json()['id'], first.json()['id'])
        self.db.add(GroupMember(group_id=self.group.id, profile_id=self.other.id,
            role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE))
        guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name='Convidado teste')
        self.db.add(guest)
        await self.db.flush()
        self.db.add(EventPresence(event_id=event.id, guest_id=guest.id,
            status=PresenceStatus.WAITLIST, waitlist_position=1))
        await self.db.flush()
        token = (await self.login(self.other, 'test-password-456')).json()['access_token']
        waiting = await self.client.post(url, headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(waiting.status_code, 200, waiting.text)
        self.assertEqual(waiting.json()['status'], 'waitlist')
        self.assertEqual(waiting.json()['waitlist_position'], 1)
        people = (await self.client.get(f'{self.base}/events/{event.id}/confirmed', headers=self.headers)).json()
        self.assertEqual([p['name'] for p in people], [self.user.name])
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(EventPresence).where(
            EventPresence.event_id == event.id, EventPresence.profile_id == self.user.id)), 1)

    async def test_member_can_withdraw_own_confirmation_and_promote_waitlist(self):
        event = await self.event()
        self.db.add(GroupMember(group_id=self.group.id, profile_id=self.other.id,
                                role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE))
        await self.db.flush()
        token = (await self.login(self.other, 'test-password-456')).json()['access_token']
        member_headers = {'Authorization': f'Bearer {token}'}
        url = f'{self.base}/events/{event.id}'
        first = await self.client.post(url+'/confirm', headers=member_headers)
        await self.client.post(url+'/confirm', headers=self.headers)
        own_list = (await self.client.get(url+'/confirmed', headers=member_headers)).json()
        self.assertTrue(own_list[0]['can_cancel_confirmation'])
        owner_list = (await self.client.get(url+'/confirmed', headers=self.headers)).json()
        self.assertFalse(owner_list[0]['can_cancel_confirmation'])
        self.assertTrue((await self.client.get(self.base, headers=member_headers)).json()['next_event']['can_cancel_confirmation'])
        # Retirada continua disponível após o fechamento das inscrições.
        event.status = EventStatus.REGISTRATION_CLOSED
        await self.db.flush()
        withdrawn = await self.client.post(url+'/cancel-confirmation', headers=member_headers)
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        self.assertEqual(withdrawn.json()['id'], first.json()['id'])
        self.assertEqual(withdrawn.json()['status'], 'cancelled')
        self.assertIsNone(withdrawn.json()['waitlist_position'])
        people = (await self.client.get(url+'/confirmed', headers=member_headers)).json()
        self.assertEqual([p['id'] for p in people], [str(self.user.id)])
        again = await self.client.post(url+'/cancel-confirmation', headers=member_headers)
        self.assertEqual(again.json(), withdrawn.json())
        overview = (await self.client.get(self.base, headers=member_headers)).json()['next_event']
        self.assertFalse(overview['can_cancel_confirmation'])
        event.status = EventStatus.REGISTRATION_OPEN
        await self.db.flush()
        reconfirmed = await self.client.post(url+'/confirm', headers=member_headers)
        self.assertEqual(reconfirmed.json()['id'], first.json()['id'])
        self.assertEqual(reconfirmed.json()['status'], 'waitlist')
        removed_waiter = await self.client.post(url+'/cancel-confirmation', headers=member_headers)
        self.assertEqual(removed_waiter.json()['status'], 'cancelled')
        self.assertEqual((await self.client.get(url+'/confirmed', headers=self.headers)).json()[0]['id'], str(self.user.id))

    async def test_withdrawal_authorization_event_scope_and_closed_history(self):
        event = await self.event()
        url = f'{self.base}/events/{event.id}/cancel-confirmation'
        self.assertEqual((await self.client.post(url)).status_code, 401)
        token = (await self.login(self.other, 'test-password-456')).json()['access_token']
        self.assertEqual((await self.client.post(url, headers={'Authorization': f'Bearer {token}'})).status_code, 404)
        self.assertEqual((await self.client.post(url, headers=self.headers)).status_code, 404)
        self.assertEqual((await self.client.post(f'{self.base}/events/{uuid4()}/cancel-confirmation', headers=self.headers)).status_code, 404)
        await self.client.post(f'{self.base}/events/{event.id}/confirm', headers=self.headers)
        for status in [EventStatus.FINISHED, EventStatus.CANCELLED]:
            event.status = status
            await self.db.flush()
            response = await self.client.post(url, headers=self.headers)
            self.assertEqual(response.status_code, 409, response.text)
            people = (await self.client.get(f'{self.base}/events/{event.id}/confirmed', headers=self.headers)).json()
            self.assertFalse(people[0]['can_cancel_confirmation'])
            self.assertEqual(people[0]['id'], str(self.user.id))

    async def test_withdrawal_during_event_preserves_match_records(self):
        event = await self.event()
        event.max_confirmed_players = None
        await self.db.flush()
        await self.client.post(f'{self.base}/events/{event.id}/confirm', headers=self.headers)
        for name in ['Convidado A', 'Convidado B']:
            guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name=name)
            self.db.add(guest)
            await self.db.flush()
            self.db.add(EventPresence(event_id=event.id, guest_id=guest.id, status=PresenceStatus.CONFIRMED))
        await self.db.flush()
        event.status = EventStatus.IN_PROGRESS
        team = EventTeam(event_id=event.id, name='A')
        match = Match(event_id=event.id, sequence=1, status=MatchStatus.FINISHED)
        self.db.add_all([team, match])
        await self.db.flush()
        lineup = MatchLineup(match_id=match.id, team_id=team.id, profile_id=self.user.id, role=TeamPlayerRole.PLAYER)
        self.db.add(lineup)
        await self.db.flush()
        response = await self.client.post(f'{self.base}/events/{event.id}/cancel-confirmation', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(await self.db.get(MatchLineup, lineup.id))
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(EventPresence).where(
            EventPresence.event_id == event.id, EventPresence.status == PresenceStatus.CONFIRMED)), 2)

    async def test_goalkeeper_withdrawal_promotes_only_same_role(self):
        event = await self.event(min_confirmed_goalkeepers=0, max_confirmed_goalkeepers=1)
        self.db.add(GroupMember(group_id=self.group.id, profile_id=self.other.id,
                                role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE))
        await self.db.flush()
        token = (await self.login(self.other, 'test-password-456')).json()['access_token']
        member_headers = {'Authorization': f'Bearer {token}'}
        url = f'{self.base}/events/{event.id}'
        await self.client.post(url+'/confirm', json={'role': 'goalkeeper'}, headers=self.headers)
        await self.client.post(url+'/confirm', json={'role': 'goalkeeper'}, headers=member_headers)
        guest = GroupGuest(group_id=self.group.id, created_by_id=self.user.id, name='Linha')
        self.db.add(guest)
        await self.db.flush()
        line = EventPresence(event_id=event.id, guest_id=guest.id, status=PresenceStatus.CONFIRMED,
                             role=TeamPlayerRole.PLAYER)
        self.db.add(line)
        await self.db.flush()
        removed = await self.client.post(url+'/cancel-confirmation', headers=self.headers)
        self.assertEqual(removed.status_code, 200, removed.text)
        people = (await self.client.get(url+'/confirmed', headers=self.headers)).json()
        self.assertEqual({p['id'] for p in people}, {str(self.other.id), str(guest.id)})
        self.assertEqual(next(p['role'] for p in people if p['id'] == str(self.other.id)), 'goalkeeper')

    async def test_registration_windows_and_empty_group(self):
        self.assertIsNone((await self.client.get(self.base, headers=self.headers)).json()['next_event'])
        self.assertEqual((await self.client.get(f'{self.base}/rankings', headers=self.headers)).json(), [])
        for options in [
            {'status': EventStatus.REGISTRATION_CLOSED},
            {'registration_opens_at': datetime.now(timezone.utc) + timedelta(hours=2)},
            {'registration_closes_at': datetime.now(timezone.utc) - timedelta(hours=2)},
            {'days': -1},
        ]:
            event = await self.event(**options)
            result = await self.client.post(f'{self.base}/events/{event.id}/confirm', headers=self.headers)
            self.assertEqual(result.status_code, 409, result.text)

    async def test_rankings_use_finished_matches_and_group_scope(self):
        event = await self.event(days=-1, status=EventStatus.FINISHED)
        a = EventTeam(event_id=event.id, name='A')
        b = EventTeam(event_id=event.id, name='B')
        self.db.add_all([a, b])
        await self.db.flush()
        match = Match(event_id=event.id, sequence=1, status=MatchStatus.FINISHED)
        unfinished = Match(event_id=event.id, sequence=2, status=MatchStatus.SCHEDULED)
        self.db.add_all([match, unfinished])
        await self.db.flush()
        self.db.add_all([
            MatchTeam(match_id=match.id, team_id=a.id, goals=2, result=MatchResult.WIN),
            MatchTeam(match_id=match.id, team_id=b.id, goals=1, result=MatchResult.LOSS),
            MatchLineup(match_id=match.id, team_id=a.id, profile_id=self.user.id, role=TeamPlayerRole.GOALKEEPER),
            GameAction(match_id=match.id, team_id=a.id, player_id=self.user.id, action_type=GameActionType.GOAL),
            GameAction(match_id=match.id, team_id=a.id, player_id=self.user.id, action_type=GameActionType.GOAL),
            GameAction(match_id=match.id, team_id=a.id, player_id=self.user.id, action_type=GameActionType.ASSIST),
            GameAction(match_id=unfinished.id, team_id=a.id, player_id=self.user.id, action_type=GameActionType.GOAL),
        ])
        await self.db.flush()
        result = await self.client.get(f'{self.base}/rankings', headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()), 1)
        row = result.json()[0]
        self.assertEqual((row['goals'], row['assists'], row['wins'], row['goals_conceded'], row['matches']), (2, 1, 1, 1, 1))
        table = (await self.client.get(f'{self.base}/standings', headers=self.headers)).json()
        self.assertEqual((table[0]['points'], table[0]['wins'], table[0]['draws'], table[0]['losses']), (3, 1, 0, 0))
        empty = PeladaGroup(name='Outro grupo', created_by_id=self.user.id)
        self.db.add(empty)
        await self.db.flush()
        self.assertEqual((await self.client.get(f'/my-groups/{empty.id}/rankings', headers=self.headers)).json(), [])

    async def test_member_profile_access_and_public_fields(self):
        url = self.base + f'/members/{self.user.id}'
        result = await self.client.get(url, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(set(result.json()), {'id', 'name', 'positions', 'trophies', 'can_rate'})
        self.assertTrue(result.json()['can_rate'])
        self.assertEqual(result.json()['id'], str(self.user.id))
        self.assertEqual(result.json()['trophies']['total'], 0)
        self.assertEqual((await self.client.get(self.base + f'/members/{self.other.id}', headers=self.headers)).status_code, 404)
        outsider = (await self.login(self.other, 'test-password-456')).json()['access_token']
        self.assertEqual((await self.client.get(url, headers={'Authorization': f'Bearer {outsider}'})).status_code, 404)
        self.assertEqual((await self.client.get(url)).status_code, 401)
