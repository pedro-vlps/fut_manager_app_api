from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, Field, field_validator
from src.schemas.player_positions import PlayerPositions
from pydantic_core import PydanticCustomError
from src.helpers.password_policy import missing_password_requirements


def validate_new_password(value):
    if value is None:
        raise PydanticCustomError('password_required', 'Informe uma senha válida.')
    missing = missing_password_requirements(value)
    if missing:
        raise PydanticCustomError('password_requirements', 'A senha precisa conter: {requirements}.',
                                  {'requirements': ', '.join(missing)})
    return value


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

    @field_validator('password')
    @classmethod
    def password_requirements(cls, value):
        return validate_new_password(value)

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "João Silva",
                "email": "joao@example.com",
                "password": "Senha-segura1!",
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

    @field_validator('password')
    @classmethod
    def password_requirements(cls, value):
        return validate_new_password(value)
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "João da Silva"}}
