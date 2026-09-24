from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel


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
