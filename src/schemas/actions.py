from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, model_validator
from src.models.enums import GameActionType


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
