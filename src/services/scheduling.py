from sqlalchemy import select
from src.models.entities import PeladaEvent, PeladaGroup
from src.services.base import DatabaseService


class SchedulingService(DatabaseService):
    async def lock_group(self, group):
        return await self.db.scalar(select(PeladaGroup).where(PeladaGroup.id == group.id).with_for_update())

    async def successor(self, event):
        return await self.db.scalar(select(PeladaEvent).where(PeladaEvent.recurrence_parent_id == event.id))
