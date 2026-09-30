import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from src.controllers.seasons import synchronize
from src.services.seasons import SeasonsService
from src.models.entities import GroupSeason, PeladaGroup, GroupMember, PeladaEvent, EventTeam, Match, MatchTeam, MatchLineup, GameAction
from src.models.enums import GroupRole, MembershipStatus, EventStatus, MatchStatus, MatchResult, TeamPlayerRole, GameActionType
from src.routers.seasons import router as seasons_router
from src.routers.groups import router as groups_router
from tests.test_auth import AuthTestCase


class SeasonsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = AuthTestCase.asyncSetUp
    asyncTearDown = AuthTestCase.asyncTearDown
    login = AuthTestCase.login

    async def setup_group(self, enabled=False):
        self.app.include_router(seasons_router)
        self.app.include_router(groups_router)
        self.group = PeladaGroup(name="Temporadas teste", created_by_id=self.user.id, seasons_enabled=enabled, season_duration_days=1)
        self.db.add(self.group)
        await self.db.flush()
        self.base = f"/my-groups/{self.group.id}"
        self.headers = {"Authorization": "Bearer " + (await self.login()).json()["access_token"]}

    async def scored_match(self, ended_at, goals):
        event = PeladaEvent(group_id=self.group.id, created_by_id=self.user.id, title="Partida de temporada", scheduled_at=ended_at - timedelta(hours=2), status=EventStatus.FINISHED)
        self.db.add(event)
        await self.db.flush()
        a, b = EventTeam(event_id=event.id, name="A"), EventTeam(event_id=event.id, name="B")
        match = Match(event_id=event.id, sequence=1, status=MatchStatus.FINISHED, started_at=ended_at - timedelta(hours=2), ended_at=ended_at)
        self.db.add_all([a, b, match])
        await self.db.flush()
        self.db.add_all([
            MatchTeam(match_id=match.id, team_id=a.id, goals=goals, result=MatchResult.WIN),
            MatchTeam(match_id=match.id, team_id=b.id, goals=0, result=MatchResult.LOSS),
            MatchLineup(match_id=match.id, team_id=a.id, profile_id=self.user.id, role=TeamPlayerRole.PLAYER),
        ])
        for _ in range(goals):
            self.db.add(GameAction(match_id=match.id, team_id=a.id, player_id=self.user.id, action_type=GameActionType.GOAL))
        await self.db.flush()

    async def test_rollover_boundaries_history_snapshots_and_group_isolation(self):
        await self.setup_group(True)
        now = datetime.now(timezone.utc)
        anchor = now - timedelta(days=2, hours=12)
        first = GroupSeason(group_id=self.group.id, number=1, starts_at=anchor, ends_at=anchor+timedelta(days=1))
        self.db.add(first)
        await self.db.flush()
        await self.scored_match(anchor + timedelta(hours=1), 1)
        await self.scored_match(first.ends_at, 2)  # No limite, conta apenas na próxima.
        await self.scored_match(now - timedelta(hours=1), 3)
        await self.scored_match(anchor - timedelta(hours=1), 4)  # Antes de ativar.
        result = await self.client.get(self.base + '/season-rankings', headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['season']['number'], 3)
        self.assertEqual(result.json()['rankings'][0]['goals'], 3)
        self.assertEqual(result.json()['rankings'][0]['matches'], 1)
        history = (await self.client.get(self.base + '/seasons', headers=self.headers)).json()['seasons']
        self.assertEqual([s['number'] for s in history], [2, 1])
        url = self.base + f'/seasons/{first.id}/rankings'
        self.assertEqual((await self.client.get(url, headers=self.headers)).json()['rankings'][0]['goals'], 1)
        second = (await self.client.get(self.base + f"/seasons/{history[0]['id']}/rankings", headers=self.headers)).json()
        self.assertEqual(second['rankings'][0]['goals'], 2)
        await self.scored_match(anchor + timedelta(hours=3), 5)
        self.assertEqual((await self.client.get(url, headers=self.headers)).json()['rankings'][0]['goals'], 1)
        outsider = {"Authorization": "Bearer " + (await self.login(self.other, 'test-password-456')).json()['access_token']}
        self.assertEqual((await self.client.get(url, headers=outsider)).status_code, 404)
        other_group = PeladaGroup(name='Outro', created_by_id=self.user.id)
        self.db.add(other_group)
        await self.db.flush()
        self.assertEqual((await self.client.get(f'/my-groups/{other_group.id}/seasons/{first.id}/rankings', headers=self.headers)).status_code, 404)
        self.assertEqual((await self.client.get(self.base + '/seasons', headers=self.headers)).json()['seasons'], history)

    async def test_optional_settings_permissions_disable_and_reenable(self):
        await self.setup_group()
        await self.scored_match(datetime.now(timezone.utc) - timedelta(days=1), 2)
        result = (await self.client.get(self.base + '/season-rankings', headers=self.headers)).json()
        self.assertIsNone(result['season'])
        self.assertEqual(result['rankings'][0]['goals'], 2)
        url = self.base + '/settings'
        payload = {'enabled': True, 'duration_days': 30}
        membership = GroupMember(group_id=self.group.id, profile_id=self.other.id, role=GroupRole.MEMBER, status=MembershipStatus.ACTIVE)
        self.db.add(membership)
        await self.db.flush()
        headers = {"Authorization": "Bearer " + (await self.login(self.other, 'test-password-456')).json()['access_token']}
        self.assertEqual((await self.client.post(url, json=payload, headers=headers)).status_code, 403)
        membership.role = GroupRole.ADMIN
        await self.db.flush()
        for days in [0, -1, 3651, 1.5]:
            self.assertEqual((await self.client.post(url, json={**payload, 'duration_days': days}, headers=headers)).status_code, 422)
        enabled = await self.client.post(url, json=payload, headers=headers)
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.assertEqual((await self.client.get(self.base + '/season-rankings', headers=self.headers)).json()['rankings'], [])
        disabled = await self.client.post(url, json={**payload, 'enabled': False}, headers=self.headers)
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertIsNone(disabled.json()['current_season'])
        self.assertEqual(len((await self.client.get(self.base + '/seasons', headers=self.headers)).json()['seasons']), 1)
        self.assertEqual((await self.client.get(self.base + '/rankings', headers=self.headers)).json()[0]['goals'], 2)
        restarted = (await self.client.post(url, json=payload, headers=self.headers)).json()
        self.assertEqual(restarted['current_season']['number'], 2)

    async def test_duration_change_applies_next_period_and_empty_periods_reset(self):
        await self.setup_group()
        response = await self.client.post(self.base + '/settings', json={'enabled':True, 'duration_days':1}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        previous_end = response.json()['current_season']['ends_at']
        updated = (await self.client.post(self.base + '/settings', json={'enabled':True, 'duration_days':7}, headers=self.headers)).json()
        self.assertEqual(updated['current_season']['ends_at'], previous_end)
        boundary = datetime.fromisoformat(previous_end.replace('Z', '+00:00'))
        service = SeasonsService(self.db)
        _, current = await synchronize(service, self.group.id, boundary)
        self.assertEqual(current.number, 2)
        self.assertEqual(current.starts_at, boundary)
        self.assertEqual(current.ends_at - current.starts_at, timedelta(days=7))
        _, later = await synchronize(service, self.group.id, boundary + timedelta(days=21))
        self.assertEqual(later.number, 5)
        archived = await service.history(self.group.id)
        self.assertEqual(len(archived), 4)
        self.assertTrue(all(s.archived_rankings == [] for s in archived))

    async def test_monthly_calendar_and_fixed_date(self):
        from zoneinfo import ZoneInfo
        from src.helpers.season_calendar import period_end
        await self.setup_group()
        url = self.base + '/settings'
        body = dict(enabled=True, mode='months', months=3, day=10, timezone='America/Sao_Paulo')
        result = await self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        end = datetime.fromisoformat(data['current_season']['ends_at'].replace('Z', '+00:00'))
        self.assertEqual(end.astimezone(ZoneInfo('America/Sao_Paulo')).day, 10)
        service = SeasonsService(self.db)
        _, second = await synchronize(service, self.group.id, end)
        self.assertEqual(second.number, 2)
        self.assertEqual(second.starts_at, end)
        self.assertEqual(second.ends_at, period_end(self.group, end))
        # Dia 31 se adapta a fevereiro, sem perder o dia 31 nos meses seguintes.
        self.group.season_months = 1
        self.group.season_day = 31
        jan = datetime(2028, 1, 31, tzinfo=ZoneInfo('America/Sao_Paulo'))
        feb = period_end(self.group, jan)
        mar = period_end(self.group, feb)
        self.assertEqual((feb.month, feb.day), (2, 29))
        self.assertEqual((mar.month, mar.day), (3, 31))
        dec = datetime(2028, 12, 31, tzinfo=ZoneInfo('America/Sao_Paulo'))
        self.assertEqual(period_end(self.group, dec).year, 2029)

    async def test_fixed_end_archives_without_new_season_and_validates(self):
        await self.setup_group()
        url = self.base + '/settings'
        end = datetime.now(timezone.utc) + timedelta(days=10)
        body = dict(enabled=True, mode='fixed', fixed_end=end.isoformat())
        for changes in [dict(fixed_end=None), dict(fixed_end='2000-01-01T00:00:00Z'), dict(timezone='invalid'), dict(mode='months', months=0), dict(mode='months', day=32)]:
            response = await self.client.post(url, json={**body, **changes}, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        original = response.json()['current_season']
        changed_end = end + timedelta(days=5)
        updated = await self.client.post(url, json={**body, 'fixed_end': changed_end.isoformat()}, headers=self.headers)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['current_season']['id'], original['id'])
        self.assertEqual(updated.json()['current_season']['starts_at'], original['starts_at'])
        service = SeasonsService(self.db)
        group, season = await synchronize(service, self.group.id, changed_end)
        self.assertFalse(group.seasons_enabled)
        self.assertIsNone(season)
        self.assertEqual(len(await service.history(group.id)), 1)
        _, season = await synchronize(service, self.group.id, changed_end + timedelta(days=30))
        self.assertIsNone(season)
