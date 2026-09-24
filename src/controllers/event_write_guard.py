"""Validação do evento relacionado a uma operação do CRUD genérico."""

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import (
    EventPresence,
    EventTeam,
    EventTeamPlayer,
    EventTeamQueueEntry,
    GameAction,
    GroupGuest,
    GroupMember,
    Match,
    MatchLineup,
    MatchTeam,
    PeladaEvent,
    PeladaGroup,
)
from src.models.enums import EventStatus
from src.helpers.identifiers import parse_uuid
from src.services.event_write_guard import EventWriteGuardService

EVENT_MODELS = {
    PeladaEvent,
    EventPresence,
    EventTeam,
    EventTeamPlayer,
    EventTeamQueueEntry,
    Match,
    MatchLineup,
    MatchTeam,
    GameAction,
    PeladaGroup,
    GroupGuest,
}


async def referenced_events(service, values):
    ids = set()
    if values.get("event_id"):
        ids.add(parse_uuid(values["event_id"]))
    for field, parent in [("team_id", EventTeam), ("match_id", Match)]:
        if values.get(field):
            item = await service.get(parent, parse_uuid(values[field]))
            if item:
                ids.add(item.event_id)
    return ids


async def check_write(model, request: Request, db: AsyncSession):
    service = EventWriteGuardService(db)
    if model is GroupMember and request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise HTTPException(403, "Use o fluxo autenticado de pedidos de entrada para adicionar membros.")
    if request.method in {"GET", "HEAD", "OPTIONS"} or model not in EVENT_MODELS:
        return
    ids = set()
    identifier = request.path_params.get("id_")
    if identifier:
        item = await service.get(model, parse_uuid(identifier))
        if item:
            if model is PeladaEvent:
                ids.add(item.id)
            else:
                ids.update(
                    await referenced_events(
                        service,
                        {
                            key: getattr(item, key, None)
                            for key in ["event_id", "team_id", "match_id"]
                        },
                    )
                )
            if request.method == "DELETE":
                if model is PeladaGroup:
                    ids.update(await service.group_event_ids(item.id))
                elif model is GroupGuest:
                    ids.update(await service.guest_event_ids(item.id))
    if request.method in {"POST", "PATCH", "PUT"}:
        body = await request.json()
        for row in body if isinstance(body, list) else [body]:
            if isinstance(row, dict):
                ids.update(await referenced_events(service, row))
    if ids:
        events = await service.locked_events(ids)
        if any(
            (e.status in {EventStatus.FINISHED, EventStatus.CANCELLED} for e in events)
        ):
            raise HTTPException(
                409,
                "Evento encerrado: partidas, jogadores e súmulas são somente para consulta.",
            )
