"""Consultas usadas pela proteção de escrita do CRUD."""

from sqlalchemy import select
from src.models.entities import PeladaEvent, EventPresence
from src.services.base import DatabaseService


class EventWriteGuardService(DatabaseService):

    async def group_event_ids(self, group_id):
        return (
            await self.db.scalars(
                select(PeladaEvent.id).where(PeladaEvent.group_id == group_id)
            )
        ).all()

    async def guest_event_ids(self, guest_id):
        return (
            await self.db.scalars(
                select(EventPresence.event_id).where(EventPresence.guest_id == guest_id)
            )
        ).all()

    async def locked_events(self, ids):
        return (
            await self.db.scalars(
                select(PeladaEvent)
                .where(PeladaEvent.id.in_(ids))
                .order_by(PeladaEvent.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
