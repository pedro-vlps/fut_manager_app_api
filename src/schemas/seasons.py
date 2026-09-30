from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from src.schemas.groups import RankingEntry


class SeasonSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: int
    starts_at: datetime
    ends_at: datetime


class SeasonSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    duration_days: int = Field(default=30, ge=1, le=3650, strict=True)
    mode: Literal["days", "months", "fixed"] = "days"
    months: int = Field(default=3, ge=1, le=120, strict=True)
    day: int = Field(default=10, ge=1, le=31, strict=True)
    fixed_end: AwareDatetime | None = None
    timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=80)


class SeasonSettings(BaseModel):
    enabled: bool
    duration_days: int
    mode: str
    months: int
    day: int
    fixed_end: datetime | None
    timezone: str
    current_season: SeasonSchema | None
    can_manage: bool


class SeasonHistory(BaseModel):
    seasons: list[SeasonSchema]


class SeasonRankings(BaseModel):
    season: SeasonSchema | None
    rankings: list[RankingEntry]
