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
        for suffix in ['', '/history', '/members', '/rankings', f'/events/{upcoming.id}/confirmed']:
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
        empty = PeladaGroup(name='Outro grupo', created_by_id=self.user.id)
        self.db.add(empty)
        await self.db.flush()
        self.assertEqual((await self.client.get(f'/my-groups/{empty.id}/rankings', headers=self.headers)).json(), [])
