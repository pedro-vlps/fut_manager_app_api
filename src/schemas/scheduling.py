from uuid import UUID
from typing import Literal
from pydantic import Field, AwareDatetime, model_validator
from src.schemas.events import ConfirmationSettings
from src.schemas.registration_window import validate_registration_window


class ScheduleRequest(ConfirmationSettings):
    modality: Literal["campo", "futsal", "fut7"] = "campo"
    id: UUID
    title: str = Field(min_length=1, max_length=150)
    scheduled_at: AwareDatetime
    registration_opens_at: AwareDatetime | None = None
    registration_closes_at: AwareDatetime | None = None
    min_confirmed_players: int = Field(ge=3, le=1000)
    recurring_weekly: bool = False
    schedule_timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=80)

    @model_validator(mode="after")
    def valid_registration_window(self):
        validate_registration_window(self.scheduled_at, self.registration_opens_at, self.registration_closes_at)
        return self
