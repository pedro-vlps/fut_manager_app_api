from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel
from src.models.enums import EventStatus


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
