from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, Field, field_validator
from src.schemas.player_positions import PlayerPositions
from pydantic_core import PydanticCustomError


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
