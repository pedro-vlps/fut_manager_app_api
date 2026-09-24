from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel


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
