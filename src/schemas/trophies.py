from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class TrophySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    season_id: UUID | None = None
    championship_id: UUID | None = None
    category: str
    title: str
    value: int
    awarded_at: datetime


class TrophyCount(BaseModel):
    category: str
    name: str
    count: int


class TrophyCollection(BaseModel):
    total: int
    summary: list[TrophyCount]
    trophies: list[TrophySchema]
