from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel
from src.models.enums import MatchStatus


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
