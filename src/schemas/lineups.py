from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, model_validator
from src.models.enums import TeamPlayerRole


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
