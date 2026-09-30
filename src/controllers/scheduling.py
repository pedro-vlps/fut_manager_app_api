from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from src.models.entities import PeladaEvent
from src.models.enums import EventStatus
from src.controllers.lifecycle_support import can_manage
from src.schemas.events import PeladaEventSchema
from src.services.scheduling import SchedulingService


async def schedule(payload, group, profile, db):
    if not await can_manage(db, group, profile):
        raise HTTPException(403, "Somente owners e administradores podem agendar eventos.")
    service = SchedulingService(db)
    try:
        ZoneInfo(payload.schedule_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Fuso horário inválido.")
    await service.lock_group(group)
    existing = await service.get(PeladaEvent, payload.id)
    if existing:
        if any(getattr(existing, key) != getattr(payload, key) for key in (
            "max_confirmed_players", "min_confirmed_goalkeepers", "max_confirmed_goalkeepers"
        )):
            raise HTTPException(409, "Este identificador já foi usado. Atualize a tela.")
        if (existing.group_id, existing.created_by_id, existing.title, existing.scheduled_at,
            existing.min_confirmed_players, existing.recurring_weekly, existing.schedule_timezone, existing.modality) != (
            group.id, profile.id, payload.title.strip(), payload.scheduled_at,
            payload.min_confirmed_players, payload.recurring_weekly, payload.schedule_timezone, payload.modality):
            raise HTTPException(409, "Este identificador já foi usado. Atualize a tela.")
        return PeladaEventSchema.model_validate(existing)
    if not payload.title.strip():
        raise HTTPException(422, "Informe o título do evento.")
    if payload.scheduled_at < datetime.now(timezone.utc) + timedelta(hours=1):
        raise HTTPException(422, "O evento deve ser agendado com pelo menos 1 hora de antecedência, inclusive para hoje.")
    event = PeladaEvent(**payload.model_dump(exclude={"title"}), title=payload.title.strip(),
        group_id=group.id, created_by_id=profile.id, status=EventStatus.REGISTRATION_OPEN)
    service.add(event)
    await service.flush()
    result = PeladaEventSchema.model_validate(event)
    await service.commit()
    return result


async def schedule_next(db, event):
    # O encerramento mantém o evento bloqueado até o commit, incluindo seu sucessor.
    if not event.recurring_weekly:
        return
    service = SchedulingService(db)
    if await service.successor(event):
        return
    next_date = event.scheduled_at.astimezone(ZoneInfo(event.schedule_timezone)) + timedelta(weeks=1)
    service.add(PeladaEvent(group_id=event.group_id, created_by_id=event.created_by_id,
        modality=event.modality, title=event.title, location=event.location, scheduled_at=next_date,
        min_confirmed_players=event.min_confirmed_players, max_confirmed_players=event.max_confirmed_players,
        min_confirmed_goalkeepers=event.min_confirmed_goalkeepers,
        max_confirmed_goalkeepers=event.max_confirmed_goalkeepers,
        match_duration_minutes=event.match_duration_minutes,
        recurring_weekly=True, schedule_timezone=event.schedule_timezone, recurrence_parent_id=event.id,
        status=EventStatus.REGISTRATION_OPEN))
