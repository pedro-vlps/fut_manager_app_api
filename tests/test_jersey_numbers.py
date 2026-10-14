"""Contratos e montagem da seleção de jogadores, sem depender do banco."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from src.models.enums import EventStatus, MatchStatus, PresenceStatus, TeamPlayerRole
from src.schemas.jersey_numbers import JerseyNumberRequest
from src.schemas.lifecycle import PlayerSelection, TeamsRequest
from src.models.entities import EventTeamPlayer
from src.schemas.team_players import EventTeamPlayerCreateSchema, EventTeamPlayerUpdateSchema
from src.controllers import lifecycle, lifecycle_support, championships


class JerseyNumberSchemaTests(unittest.TestCase):
    def test_boundaries_and_removal(self):
        for number in (None, 0, 1, 99, 100):
            with self.subTest(number=number):
                self.assertEqual(JerseyNumberRequest(jersey_number=number).jersey_number, number)
                self.assertEqual(PlayerSelection(presence_id=uuid4(), jersey_number=number).jersey_number, number)
                self.assertEqual(EventTeamPlayerCreateSchema(team_id=uuid4(), profile_id=uuid4(), jersey_number=number).jersey_number, number)
                self.assertEqual(EventTeamPlayerUpdateSchema(jersey_number=number).jersey_number, number)

    def test_invalid_values_are_rejected(self):
        for number in (-1, 101, 1.5, True, '10', ''):
            for schema, fields in ((JerseyNumberRequest, {}), (PlayerSelection, {'presence_id': uuid4()}),
                                   (EventTeamPlayerUpdateSchema, {})):
                with self.subTest(number=number, schema=schema):
                    with self.assertRaises(ValidationError):
                        schema(**fields, jersey_number=number)

    def test_update_requires_explicit_number(self):
        with self.assertRaises(ValidationError):
            JerseyNumberRequest()


class JerseyNumberControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_rebuilding_teams_preserves_numbers_and_accepts_explicit_changes(self):
        event = SimpleNamespace(id=uuid4(), status=EventStatus.REGISTRATION_CLOSED, min_confirmed_goalkeepers=None)
        people = [SimpleNamespace(id=uuid4(), profile_id=uuid4(), guest_id=None, role=TeamPlayerRole.PLAYER) for _ in range(6)]
        previous = [SimpleNamespace(profile_id=p.profile_id, guest_id=None, jersey_number=i * 10) for i, p in enumerate(people)]
        payload = TeamsRequest(mode='manual', teams=[{'name': f'Time {i}', 'players': [
            {'presence_id': p.id, **({'jersey_number': None} if j == 0 else {'jersey_number': 100} if j == 1 else {})}
            for j, p in enumerate(people) if j % 3 == i]} for i in range(3)])
        service = SimpleNamespace(first_match_id=AsyncMock(return_value=None), confirmed_players=AsyncMock(return_value=people),
                                  event_players=AsyncMock(return_value=previous), delete_event_queue=AsyncMock(),
                                  delete_event_players=AsyncMock(), delete_event_teams=AsyncMock(), add=Mock(), flush=AsyncMock())
        with patch.object(lifecycle, 'LifecycleService', return_value=service), patch.object(lifecycle, 'save', new=AsyncMock()), \
                patch.object(lifecycle, 'confirmed_players', new=AsyncMock(return_value=people)):
            await lifecycle.build_teams(payload, event, None)
        assigned = {call.args[0].profile_id: call.args[0].jersey_number for call in service.add.call_args_list
                    if isinstance(call.args[0], EventTeamPlayer)}
        self.assertIsNone(assigned[people[0].profile_id])
        self.assertEqual(assigned[people[1].profile_id], 100)
        self.assertEqual([assigned[p.profile_id] for p in people[2:]], [20, 30, 40, 50])

    async def test_event_update_and_removal(self):
        event = SimpleNamespace(id=uuid4())
        person = SimpleNamespace(id=uuid4(), event_id=event.id, profile_id=uuid4(), guest_id=None)
        team = SimpleNamespace(id=uuid4(), event_id=event.id)
        player = SimpleNamespace(profile_id=person.profile_id, guest_id=None, jersey_number=None)
        service = SimpleNamespace(get=AsyncMock(side_effect=[person, team, person, team]),
                                  players_for_teams=AsyncMock(return_value=[player]))
        with patch.object(lifecycle, 'LifecycleService', return_value=service), patch.object(lifecycle, 'save', new=AsyncMock()):
            await lifecycle.set_jersey_number(team.id, person.id, JerseyNumberRequest(jersey_number=0), event, None)
            self.assertEqual(player.jersey_number, 0)
            await lifecycle.set_jersey_number(team.id, person.id, JerseyNumberRequest(jersey_number=None), event, None)
            self.assertIsNone(player.jersey_number)

    async def test_cross_event_update_is_rejected(self):
        event = SimpleNamespace(id=uuid4())
        person = SimpleNamespace(event_id=uuid4())
        team = SimpleNamespace(event_id=event.id)
        service = SimpleNamespace(get=AsyncMock(side_effect=[person, team]))
        with patch.object(lifecycle, 'LifecycleService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await lifecycle.set_jersey_number(uuid4(), uuid4(), JerseyNumberRequest(jersey_number=10), event, None)
        self.assertEqual(error.exception.status_code, 404)

    async def test_club_requires_owner(self):
        club = SimpleNamespace(id=uuid4(), owner_id=uuid4())
        service = SimpleNamespace(locked=AsyncMock(return_value=club))
        with patch.object(championships, 'ChampionshipsService', return_value=service):
            with self.assertRaises(HTTPException) as error:
                await championships.set_club_jersey_number(club.id, uuid4(), JerseyNumberRequest(jersey_number=10), SimpleNamespace(id=uuid4()), None)
        self.assertEqual(error.exception.status_code, 403)

    async def test_event_requires_manager(self):
        with patch.object(lifecycle, 'can_manage', new=AsyncMock(return_value=False)):
            with self.assertRaises(HTTPException) as error:
                await lifecycle.managed_event(uuid4(), None, None, None)
        self.assertEqual(error.exception.status_code, 403)

    async def test_snapshot_includes_zero_and_guest_number_in_match(self):
        event = SimpleNamespace(id=uuid4(), group_id=uuid4(), created_by_id=uuid4(), title='Teste',
                                scheduled_at=datetime.now(timezone.utc), status=EventStatus.IN_PROGRESS,
                                modality='fut7', min_confirmed_goalkeepers=None)
        team = SimpleNamespace(id=uuid4(), name='Time', color=None)
        match = SimpleNamespace(id=uuid4(), sequence=1, status=MatchStatus.IN_PROGRESS, advancing_team_id=None,
                                timer_elapsed_ms=0, timer_running_since=None)
        people, players, lineups = [], [], []
        for guest, number in ((False, 0), (True, 100)):
            person = SimpleNamespace(id=uuid4(), profile_id=None if guest else uuid4(), guest_id=uuid4() if guest else None,
                                     role=TeamPlayerRole.PLAYER, status=PresenceStatus.CONFIRMED)
            people.append((person, None if guest else 'Jogador', 'Convidado' if guest else None, {}))
            players.append(SimpleNamespace(profile_id=person.profile_id, guest_id=person.guest_id, team_id=team.id,
                                            role=person.role, jersey_number=number))
            # O convidado participa temporariamente por outro time e mantém seu número.
            lineups.append(SimpleNamespace(profile_id=person.profile_id, guest_id=person.guest_id,
                                            team_id=uuid4() if guest else team.id, match_id=match.id, role=person.role,
                                            is_active=True, replaced_lineup_id=uuid4() if guest else None))
        service = SimpleNamespace(**{key: AsyncMock(return_value=value) for key, value in {
            'event_people': people, 'event_teams': [team], 'event_players': players, 'event_matches': [match],
            'event_scores': [], 'event_actions': [], 'event_lineups': lineups, 'waiting_team_ids': [],
        }.items()})
        with patch.object(lifecycle_support, 'LifecycleService', return_value=service):
            result = await lifecycle_support.snapshot(None, event, True)
        self.assertEqual([p.jersey_number for p in result.teams[0].players], [0, 100])
        self.assertEqual([p.jersey_number for p in result.current_match.players], [0, 100])
        self.assertTrue(result.current_match.players[1].is_temporary)
