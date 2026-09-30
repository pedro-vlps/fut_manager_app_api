from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, model_validator
from src.models.enums import PresenceStatus, TeamPlayerRole


class ConfirmRequest(SCBaseModel):
    role: TeamPlayerRole = TeamPlayerRole.PLAYER


class EventPresenceSchema(SCBaseModel):
    role: TeamPlayerRole = TeamPlayerRole.PLAYER
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
    role: TeamPlayerRole = TeamPlayerRole.PLAYER
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
    role: TeamPlayerRole | None = None
    status: Optional[PresenceStatus] = None
    waitlist_position: Optional[int] = None
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"status": "confirmed"}}
