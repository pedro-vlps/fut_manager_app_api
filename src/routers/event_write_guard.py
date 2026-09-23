"""Impede que o CRUD genérico altere eventos encerrados ou seus registros."""
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.configs.db_connection import get_db_session
from src.models.entities import (EventPresence, EventTeam, EventTeamPlayer, EventTeamQueueEntry,
    GameAction, GroupGuest, Match, MatchLineup, MatchTeam, PeladaEvent, PeladaGroup)
from src.models.enums import EventStatus

EVENT_MODELS = {PeladaEvent, EventPresence, EventTeam, EventTeamPlayer, EventTeamQueueEntry,
    Match, MatchLineup, MatchTeam, GameAction, PeladaGroup, GroupGuest}


def event_write_guard(model):
    async def guard(request: Request, db: AsyncSession = Depends(get_db_session)):
        if request.method in {'GET', 'HEAD', 'OPTIONS'} or model not in EVENT_MODELS:
            return
        ids = set()

        def uuid(value):
            try:
                return UUID(str(value))
            except (ValueError, TypeError):
                raise HTTPException(422, 'Identificador inválido.')

        async def references(values):
            if values.get('event_id'):
                ids.add(uuid(values['event_id']))
            for field, parent in [('team_id', EventTeam), ('match_id', Match)]:
                if values.get(field):
                    item = await db.get(parent, uuid(values[field]))
                    if item:
                        ids.add(item.event_id)

        identifier = request.path_params.get('id_')
        if identifier:
            item = await db.get(model, uuid(identifier))
            if item:
                if model is PeladaEvent:
                    ids.add(item.id)
                else:
                    await references({key:getattr(item, key, None) for key in ['event_id','team_id','match_id']})
                if request.method == 'DELETE' and model in {PeladaGroup, GroupGuest}:
                    # Estas exclusões propagam para eventos ou participantes do histórico.
                    if model is PeladaGroup:
                        query = select(PeladaEvent.id).where(PeladaEvent.group_id == item.id)
                    else:
                        query = select(EventPresence.event_id).where(EventPresence.guest_id == item.id)
                    ids.update((await db.scalars(query)).all())
        if request.method in {'POST', 'PATCH', 'PUT'}:
            body = await request.json()
            rows = body if isinstance(body, list) else [body]
            for row in rows:
                if isinstance(row, dict):
                    await references(row)
        if ids:
            # Compartilha a sessão da rota CRUD: o lock dura até o commit da escrita.
            events = (await db.scalars(select(PeladaEvent).where(PeladaEvent.id.in_(ids))
                .order_by(PeladaEvent.id).with_for_update().execution_options(populate_existing=True))).all()
            if any(e.status in {EventStatus.FINISHED, EventStatus.CANCELLED} for e in events):
                raise HTTPException(409, 'Evento encerrado: partidas, jogadores e súmulas são somente para consulta.')
    return guard
