from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel as SCBaseModel, Field, model_validator
from src.models.enums import EventStatus


class PeladaEventSchema(SCBaseModel):
    min_confirmed_goalkeepers: int | None = None
    max_confirmed_goalkeepers: int | None = None
    id: Optional[UUID] = None
    group_id: UUID
    created_by_id: UUID
    title: str
    location: Optional[str] = None
    scheduled_at: datetime
    modality: Literal["campo", "futsal", "fut7"] | None = None
    recurring_weekly: bool = False
    schedule_timezone: str = "America/Sao_Paulo"
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: Optional[int] = None
    max_confirmed_players: Optional[int] = None
    match_duration_minutes: Optional[int] = None
    status: EventStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "title": "Pelada 21/09",
                "location": "Arena Central",
                "scheduled_at": "2026-09-21T20:00:00-03:00",
                "min_confirmed_players": 12,
                "max_confirmed_players": 18,
                "match_duration_minutes": 10,
                "status": "registration_open",
            }
        }


class PeladaEventCreateSchema(SCBaseModel):
    min_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)
    max_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)
    group_id: UUID
    created_by_id: UUID
    title: str
    location: Optional[str] = None
    scheduled_at: datetime
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: int
    max_confirmed_players: int
    match_duration_minutes: Optional[int] = None
    status: EventStatus = EventStatus.DRAFT

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "created_by_id": "550e8400-e29b-41d4-a716-446655440002",
                "title": "Pelada 21/09",
                "scheduled_at": "2026-09-21T20:00:00-03:00",
                "min_confirmed_players": 12,
                "max_confirmed_players": 18,
                "status": "registration_open",
            }
        }


class PeladaEventUpdateSchema(SCBaseModel):
    min_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)
    max_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)
    title: Optional[str] = None
    location: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    min_confirmed_players: Optional[int] = None
    max_confirmed_players: Optional[int] = None
    match_duration_minutes: Optional[int] = None
    status: Optional[EventStatus] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"status": "registration_closed"}}


class ConfirmationSettings(SCBaseModel):
    min_confirmed_players: int = Field(ge=3, le=1000)
    max_confirmed_players: int | None = Field(default=None, ge=3, le=1000)
    # NULL preserves the rules of events created before separate keeper slots.
    min_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)
    max_confirmed_goalkeepers: int | None = Field(default=None, ge=0, le=4)

    @model_validator(mode="after")
    def valid_limits(self):
        for minimum, maximum in [(self.min_confirmed_players, self.max_confirmed_players),
                                 (self.min_confirmed_goalkeepers, self.max_confirmed_goalkeepers)]:
            if maximum is not None and (minimum is None or maximum < minimum):
                raise ValueError("O limite de vagas deve ser maior ou igual ao mínimo exigido.")
        return self
