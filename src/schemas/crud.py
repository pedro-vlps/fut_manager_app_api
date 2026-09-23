"""Schemas usados pelo CRUD genérico e seus exemplos na documentação OpenAPI."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel as SCBaseModel, Field, model_validator, field_validator
from src.schemas.player_positions import PlayerPositions
from pydantic_core import PydanticCustomError

from src.models.enums import (
    EventStatus,
    GameActionType,
    GroupRole,
    MatchResult,
    MatchStatus,
    MembershipStatus,
    PresenceStatus,
    TeamPlayerRole,
)


class ProfileSchema(SCBaseModel):
    positions: dict[str, list[str]] = Field(default_factory=dict)
    id: Optional[UUID] = None
    name: str
    email: str
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "João Silva",
                "email": "joao@example.com",
                "avatar_url": None,
                "is_active": True,
            }
        }


class ProfileCreateSchema(SCBaseModel):
    positions: PlayerPositions
    name: str
    email: str
    password: str = Field(min_length=8, max_length=128)
    avatar_url: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "João Silva",
                "email": "joao@example.com",
                "password": "senha-segura",
                "positions": {"campo": ["volante", "meia"], "futsal": ["ala_direita"]},
                "is_active": True,
            }
        }


class ProfileUpdateSchema(SCBaseModel):
    positions: Optional[PlayerPositions] = None

    @field_validator("positions")
    @classmethod
    def positions_not_null(cls, value):
        if value is None:
            raise PydanticCustomError(
                "positions_required",
                "As posições não podem ser removidas. Escolha pelo menos uma.",
            )
        return value

    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "João da Silva"}}


class PeladaGroupSchema(SCBaseModel):
    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    created_by_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Pelada de Domingo",
                "description": "Jogo semanal",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        }


class PeladaGroupCreateSchema(SCBaseModel):
    name: str
    description: Optional[str] = None
    created_by_id: UUID

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "Pelada de Domingo",
                "description": "Jogo semanal",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        }


class PeladaGroupUpdateSchema(SCBaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "Pelada de Domingo - Centro"}}


class GroupMemberSchema(SCBaseModel):
    id: Optional[UUID] = None
    group_id: UUID
    profile_id: UUID
    role: GroupRole
    status: MembershipStatus
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "member",
                "status": "active",
            }
        }


class GroupMemberCreateSchema(SCBaseModel):
    group_id: UUID
    profile_id: UUID
    role: GroupRole = GroupRole.MEMBER
    status: MembershipStatus = MembershipStatus.ACTIVE

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "member",
                "status": "active",
            }
        }


class GroupMemberUpdateSchema(SCBaseModel):
    role: Optional[GroupRole] = None
    status: Optional[MembershipStatus] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"role": "admin"}}


class GroupGuestSchema(SCBaseModel):
    id: Optional[UUID] = None
    group_id: UUID
    created_by_id: UUID
    name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "name": "Carlos Convidado",
            }
        }


class GroupGuestCreateSchema(SCBaseModel):
    group_id: UUID
    created_by_id: UUID
    name: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "name": "Carlos Convidado",
            }
        }


class GroupGuestUpdateSchema(SCBaseModel):
    name: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "Carlos"}}


class PeladaEventSchema(SCBaseModel):
    id: Optional[UUID] = None
    group_id: UUID
    created_by_id: UUID
    title: str
    location: Optional[str] = None
    scheduled_at: datetime
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: Optional[int] = None
    max_confirmed_players: Optional[int] = None
    match_duration_minutes: Optional[int] = None
    status: EventStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "title": "Pelada 21/09",
                "location": "Arena Central",
                "scheduled_at": "2026-09-21T20:00:00-03:00",
                "min_confirmed_players": 12,
                "max_confirmed_players": 18,
                "match_duration_minutes": 10,
                "status": "registration_open",
            }
        }


class PeladaEventCreateSchema(SCBaseModel):
    group_id: UUID
    created_by_id: UUID
    title: str
    location: Optional[str] = None
    scheduled_at: datetime
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: int
    max_confirmed_players: int
    match_duration_minutes: Optional[int] = None
    status: EventStatus = EventStatus.DRAFT

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "title": "Pelada 21/09",
                "scheduled_at": "2026-09-21T20:00:00-03:00",
                "min_confirmed_players": 12,
                "max_confirmed_players": 18,
                "status": "registration_open",
            }
        }


class PeladaEventUpdateSchema(SCBaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: Optional[int] = None
    max_confirmed_players: Optional[int] = None
    match_duration_minutes: Optional[int] = None
    status: Optional[EventStatus] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"status": "registration_closed"}}


class EventPresenceSchema(SCBaseModel):
    id: Optional[UUID] = None
    event_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    status: PresenceStatus
    waitlist_position: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "status": "confirmed",
                "waitlist_position": None,
                "confirmed_at": "2026-09-21T18:00:00-03:00",
            }
        }


class EventPresenceCreateSchema(SCBaseModel):
    event_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    status: PresenceStatus = PresenceStatus.CONFIRMED
    confirmed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_player_reference(self) -> "EventPresenceCreateSchema":
        if (self.profile_id is None) == (self.guest_id is None):
            raise ValueError("Informe exatamente um profile_id ou guest_id.")
        return self

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "status": "confirmed",
            }
        }


class EventPresenceUpdateSchema(SCBaseModel):
    status: Optional[PresenceStatus] = None
    waitlist_position: Optional[int] = None
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"status": "confirmed"}}


class EventTeamSchema(SCBaseModel):
    id: Optional[UUID] = None
    event_id: UUID
    name: str
    color: Optional[str] = None
    draw_order: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Time Azul",
                "color": "#2563EB",
                "draw_order": 1,
            }
        }


class EventTeamCreateSchema(SCBaseModel):
    event_id: UUID
    name: str
    color: Optional[str] = None
    draw_order: Optional[int] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Time Azul",
                "color": "#2563EB",
                "draw_order": 1,
            }
        }


class EventTeamUpdateSchema(SCBaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    draw_order: Optional[int] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "Time Amarelo"}}


class EventTeamPlayerSchema(SCBaseModel):
    id: Optional[UUID] = None
    team_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    role: TeamPlayerRole
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "team_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "goalkeeper",
            }
        }


class EventTeamPlayerCreateSchema(SCBaseModel):
    team_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    role: TeamPlayerRole = TeamPlayerRole.PLAYER

    @model_validator(mode="after")
    def validate_player_reference(self) -> "EventTeamPlayerCreateSchema":
        if (self.profile_id is None) == (self.guest_id is None):
            raise ValueError("Informe exatamente um profile_id ou guest_id.")
        return self

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "team_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "goalkeeper",
            }
        }


class EventTeamPlayerUpdateSchema(SCBaseModel):
    role: Optional[TeamPlayerRole] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"role": "player"}}


class EventTeamQueueEntrySchema(SCBaseModel):
    id: Optional[UUID] = None
    event_id: UUID
    team_id: UUID
    position: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "position": 1,
            }
        }


class EventTeamQueueEntryCreateSchema(SCBaseModel):
    event_id: UUID
    team_id: UUID
    position: int

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "position": 1,
            }
        }


class EventTeamQueueEntryUpdateSchema(SCBaseModel):
    position: Optional[int] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"position": 3}}


class MatchSchema(SCBaseModel):
    id: Optional[UUID] = None
    event_id: UUID
    sequence: int
    previous_match_id: Optional[UUID] = None
    advancing_team_id: Optional[UUID] = None
    status: MatchStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "sequence": 1,
                "status": "scheduled",
                "started_at": None,
                "ended_at": None,
            }
        }


class MatchCreateSchema(SCBaseModel):
    event_id: UUID
    sequence: int
    previous_match_id: Optional[UUID] = None
    status: MatchStatus = MatchStatus.SCHEDULED
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "sequence": 1,
                "status": "scheduled",
            }
        }


class MatchUpdateSchema(SCBaseModel):
    sequence: Optional[int] = None
    advancing_team_id: Optional[UUID] = None
    status: Optional[MatchStatus] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "status": "in_progress",
                "started_at": "2026-09-21T20:00:00-03:00",
            }
        }


class MatchTeamSchema(SCBaseModel):
    id: Optional[UUID] = None
    match_id: UUID
    team_id: UUID
    goals: int
    result: Optional[MatchResult] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "goals": 3,
                "result": "win",
            }
        }


class MatchTeamCreateSchema(SCBaseModel):
    match_id: UUID
    team_id: UUID
    goals: int = 0
    result: Optional[MatchResult] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "goals": 3,
                "result": "win",
            }
        }


class MatchTeamUpdateSchema(SCBaseModel):
    goals: Optional[int] = None
    result: Optional[MatchResult] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"goals": 4, "result": "win"}}


class MatchLineupSchema(SCBaseModel):
    id: Optional[UUID] = None
    match_id: UUID
    team_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    role: TeamPlayerRole
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "profile_id": "550e8400-e29b-41d4-a716-446655440003",
                "role": "goalkeeper",
            }
        }


class MatchLineupCreateSchema(SCBaseModel):
    match_id: UUID
    team_id: UUID
    profile_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    role: TeamPlayerRole = TeamPlayerRole.PLAYER

    @model_validator(mode="after")
    def validate_player_reference(self) -> "MatchLineupCreateSchema":
        if (self.profile_id is None) == (self.guest_id is None):
            raise ValueError("Informe exatamente um profile_id ou guest_id.")
        return self

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "profile_id": "550e8400-e29b-41d4-a716-446655440003",
                "role": "goalkeeper",
            }
        }


class MatchLineupUpdateSchema(SCBaseModel):
    role: Optional[TeamPlayerRole] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"role": "player"}}


class GameActionSchema(SCBaseModel):
    id: Optional[UUID] = None
    match_id: UUID
    team_id: UUID
    player_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    action_type: GameActionType
    occurred_at: Optional[datetime] = None
    minute: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "player_id": "550e8400-e29b-41d4-a716-446655440003",
                "action_type": "goal",
                "minute": 7,
                "notes": None,
            }
        }


class GameActionCreateSchema(SCBaseModel):
    match_id: UUID
    team_id: UUID
    player_id: Optional[UUID] = None
    guest_id: Optional[UUID] = None
    action_type: GameActionType
    occurred_at: Optional[datetime] = None
    minute: Optional[int] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_player_reference(self) -> "GameActionCreateSchema":
        if (self.player_id is None) == (self.guest_id is None):
            raise ValueError("Informe exatamente um player_id ou guest_id.")
        return self

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "match_id": "550e8400-e29b-41d4-a716-446655440001",
                "team_id": "550e8400-e29b-41d4-a716-446655440002",
                "player_id": "550e8400-e29b-41d4-a716-446655440003",
                "action_type": "goal",
                "minute": 7,
            }
        }


class GameActionUpdateSchema(SCBaseModel):
    action_type: Optional[GameActionType] = None
    occurred_at: Optional[datetime] = None
    minute: Optional[int] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"minute": 8, "notes": "Correção da súmula"}}
