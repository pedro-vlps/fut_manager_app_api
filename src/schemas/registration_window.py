"""Abertura e prazo de confirmação no fuso informado pelo cliente."""
from datetime import datetime
from pydantic import AwareDatetime, BaseModel


def validate_registration_window(scheduled_at: datetime, opens_at: datetime | None, closes_at: datetime | None):
    if closes_at is not None and closes_at > scheduled_at:
        raise ValueError("O prazo de confirmação deve ser até o início do evento.")
    if opens_at is not None and opens_at >= (closes_at or scheduled_at):
        raise ValueError("A abertura das confirmações deve ser antes do prazo final e do evento.")


class RegistrationOpeningRequest(BaseModel):
    registration_opens_at: AwareDatetime | None
