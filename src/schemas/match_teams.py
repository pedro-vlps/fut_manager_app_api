from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel
from src.models.enums import MatchResult


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
