from datetime import datetime
from src.models.entities import PeladaEvent
from src.models.enums import EventStatus


def registration_error(event: PeladaEvent, now: datetime) -> str | None:
    if event.status != EventStatus.REGISTRATION_OPEN or event.scheduled_at <= now:
        return "As inscrições deste evento estão encerradas."
    if event.registration_opens_at and event.registration_opens_at > now:
        return "As inscrições deste evento ainda não abriram."
    if event.registration_closes_at and event.registration_closes_at <= now:
        return "O prazo para confirmar presença terminou."
    return None
