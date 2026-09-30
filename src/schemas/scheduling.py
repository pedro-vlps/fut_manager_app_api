from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, AwareDatetime
from src.schemas.events import ConfirmationSettings


class ScheduleRequest(ConfirmationSettings):
    modality: Literal["campo", "futsal", "fut7"] = "campo"
    id: UUID
    title: str = Field(min_length=1, max_length=150)
    scheduled_at: AwareDatetime
    min_confirmed_players: int = Field(ge=3, le=1000)
    recurring_weekly: bool = False
    schedule_timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=80)
