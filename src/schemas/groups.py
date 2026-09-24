from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, Field


class PeladaGroupSchema(SCBaseModel):
    code: str = Field(
        pattern="^[A-Z0-9]{6}$", description="Código único gerado pelo banco."
    )
    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    created_by_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Pelada de Domingo",
                "description": "Jogo semanal",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        }


class PeladaGroupCreateSchema(SCBaseModel):
    name: str
    description: Optional[str] = None
    created_by_id: UUID

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "Pelada de Domingo",
                "description": "Jogo semanal",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        }


class PeladaGroupUpdateSchema(SCBaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"name": "Pelada de Domingo - Centro"}}


from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from src.schemas.events import PeladaEventSchema
from src.schemas.presences import EventPresenceSchema


class EventOverview(PeladaEventSchema):
    confirmed_count: int
    my_presence: EventPresenceSchema | None
    can_confirm: bool
    confirmation_message: str | None


class GroupOverview(BaseModel):
    group: PeladaGroupSchema
    next_event: EventOverview | None
    can_manage: bool = False


class Person(BaseModel):
    id: UUID
    name: str
    role: str | None = None
    is_guest: bool = False


class RankingEntry(Person):
    goals: int = 0
    own_goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    wins: int = 0
    losses: int = 0
    goals_conceded: int = 0
    matches: int = 0
    goalkeeper_matches: int = 0
