from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel


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
