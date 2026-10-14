"""Valida abertura, prazo e recorrência sem acessar o banco configurado."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from src.models.enums import EventStatus
from src.schemas.scheduling import ScheduleRequest
from src.schemas.registration_window import RegistrationOpeningRequest
from src.helpers.groups import registration_error
from src.controllers import groups, lifecycle, scheduling


class RegistrationOpeningTests(unittest.TestCase):
    def test_scheduling_validates_window_and_requires_timezone(self):
        base = dict(id=uuid4(), title='Pelada', scheduled_at='2026-10-18T13:00:00Z', min_confirmed_players=6)
        payload = ScheduleRequest(**base, registration_opens_at='2026-10-15T00:00:00Z', registration_closes_at='2026-10-17T21:00:00Z')
        self.assertEqual(payload.registration_opens_at.hour, 0)
        self.assertIsNone(ScheduleRequest(**base).registration_opens_at)
        for opening, closing in [('2026-10-18T13:00:00Z', None), ('2026-10-18T14:00:00Z', None),
                                 ('2026-10-16T21:00:00Z', '2026-10-16T21:00:00Z'),
                                 ('2026-10-15T00:00:00Z', '2026-10-18T14:00:00Z'), ('2026-10-15T00:00:00', None)]:
            with self.subTest(opening=opening, closing=closing), self.assertRaises(ValidationError):
                ScheduleRequest(**base, registration_opens_at=opening, registration_closes_at=closing)

    def test_confirmation_is_blocked_until_exact_opening_and_at_deadline(self):
        opening = datetime(2026, 10, 15, tzinfo=timezone.utc)
        closing = opening + timedelta(days=2)
        event = SimpleNamespace(status=EventStatus.REGISTRATION_OPEN, registration_opens_at=opening,
                                registration_closes_at=closing, scheduled_at=closing + timedelta(hours=1))
        self.assertIsNotNone(registration_error(event, opening - timedelta(microseconds=1)))
        self.assertIsNone(registration_error(event, opening))
        self.assertIsNone(registration_error(event, closing - timedelta(microseconds=1)))
        self.assertIsNotNone(registration_error(event, closing))

    def test_removal_is_explicit_and_naive_datetime_is_rejected(self):
        self.assertIsNone(RegistrationOpeningRequest(registration_opens_at=None).registration_opens_at)
        for values in ({}, {'registration_opens_at': '2026-10-14T21:00:00'}):
            with self.assertRaises(ValidationError):
                RegistrationOpeningRequest(**values)


class RegistrationOpeningControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_persists_opening_and_rejects_changed_retry(self):
        scheduled = datetime.now(timezone.utc) + timedelta(days=3)
        payload = ScheduleRequest(id=uuid4(), title='Pelada', scheduled_at=scheduled,
                                  min_confirmed_players=6, registration_opens_at=scheduled - timedelta(days=2))
        group, profile = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
        service = SimpleNamespace(lock_group=AsyncMock(), get=AsyncMock(return_value=None),
                                  add=Mock(), flush=AsyncMock(), commit=AsyncMock())
        with patch.object(scheduling, 'SchedulingService', return_value=service), \
                patch.object(scheduling, 'can_manage', new=AsyncMock(return_value=True)):
            result = await scheduling.schedule(payload, group, profile, None)
            saved = service.add.call_args.args[0]
            self.assertEqual(result.registration_opens_at, payload.registration_opens_at)
            self.assertEqual(saved.registration_opens_at, payload.registration_opens_at)
            service.get.return_value = saved
            payload.registration_opens_at += timedelta(hours=1)
            with self.assertRaises(HTTPException) as error:
                await scheduling.schedule(payload, group, profile, None)
            self.assertEqual(error.exception.status_code, 409)

    async def test_confirm_rejects_before_opening_without_writing_presence(self):
        now = datetime.now(timezone.utc)
        event = SimpleNamespace(status=EventStatus.REGISTRATION_OPEN, registration_opens_at=now + timedelta(days=1),
                                registration_closes_at=None, scheduled_at=now + timedelta(days=2))
        service = SimpleNamespace(active_member_id=AsyncMock(return_value=uuid4()), profile_presence=AsyncMock(return_value=None), add=Mock())
        with patch.object(groups, 'GroupsService', return_value=service), patch.object(groups, 'group_event', new=AsyncMock(return_value=event)):
            with self.assertRaises(HTTPException) as error:
                await groups.confirm(uuid4(), SimpleNamespace(id=uuid4()), None, None)
            self.assertEqual(error.exception.status_code, 409)
        service.add.assert_not_called()

    async def test_update_preserves_deadline_and_does_not_rebuild_teams(self):
        scheduled = datetime(2026, 10, 18, 13, tzinfo=timezone.utc)
        event = SimpleNamespace(status=EventStatus.REGISTRATION_OPEN, scheduled_at=scheduled,
                                registration_closes_at=scheduled - timedelta(hours=1), registration_opens_at=None)
        service = SimpleNamespace(first_match_id=AsyncMock(return_value=None))
        with patch.object(lifecycle, 'LifecycleService', return_value=service), patch.object(lifecycle, 'save', new=AsyncMock()):
            payload = RegistrationOpeningRequest(registration_opens_at='2026-10-15T00:00:00Z')
            await lifecycle.update_registration_opening(payload, event, None)
            self.assertEqual(event.registration_opens_at, payload.registration_opens_at)
            self.assertEqual(event.registration_closes_at, scheduled - timedelta(hours=1))
            await lifecycle.update_registration_opening(RegistrationOpeningRequest(registration_opens_at=None), event, None)
            self.assertIsNone(event.registration_opens_at)

    async def test_update_rejects_invalid_window_or_started_event(self):
        scheduled = datetime(2026, 10, 18, 13, tzinfo=timezone.utc)
        event = SimpleNamespace(status=EventStatus.REGISTRATION_OPEN, scheduled_at=scheduled,
                                registration_closes_at=scheduled - timedelta(hours=1))
        payload = RegistrationOpeningRequest(registration_opens_at=scheduled)
        service = SimpleNamespace(first_match_id=AsyncMock(return_value=None))
        with patch.object(lifecycle, 'LifecycleService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await lifecycle.update_registration_opening(payload, event, None)
            self.assertEqual(error.exception.status_code, 422)
            event.status = EventStatus.IN_PROGRESS
            with self.assertRaises(HTTPException) as error:
                await lifecycle.update_registration_opening(payload, event, None)
            self.assertEqual(error.exception.status_code, 409)

    async def test_weekly_successor_keeps_local_opening_and_deadline_across_dst(self):
        zone = ZoneInfo('America/New_York')
        event = SimpleNamespace(id=uuid4(), group_id=uuid4(), created_by_id=uuid4(), recurring_weekly=True,
            schedule_timezone='America/New_York', scheduled_at=datetime(2026, 3, 1, 10, tzinfo=zone),
            registration_opens_at=datetime(2026, 2, 25, 21, tzinfo=zone),
            registration_closes_at=datetime(2026, 3, 1, 9, tzinfo=zone),
            modality='campo', title='Pelada', location=None, min_confirmed_players=6, max_confirmed_players=6,
            min_confirmed_goalkeepers=None, max_confirmed_goalkeepers=None, match_duration_minutes=None)
        service = SimpleNamespace(successor=AsyncMock(return_value=None), add=Mock())
        with patch.object(scheduling, 'SchedulingService', return_value=service):
            await scheduling.schedule_next(None, event)
        successor = service.add.call_args.args[0]
        self.assertEqual(successor.registration_opens_at, datetime(2026, 3, 4, 21, tzinfo=zone))
        self.assertEqual(successor.registration_closes_at, datetime(2026, 3, 8, 9, tzinfo=zone))
        self.assertEqual(successor.scheduled_at.astimezone(timezone.utc).hour, 14)
        self.assertEqual(successor.registration_closes_at.astimezone(timezone.utc).hour, 13)
