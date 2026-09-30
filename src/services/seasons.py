from sqlalchemy import select
from src.models.entities import GroupSeason
from src.services.group_requests import GroupRequestsService


class SeasonsService(GroupRequestsService):
    async def latest(self, group_id):
        return await self.db.scalar(select(GroupSeason).where(GroupSeason.group_id == group_id).order_by(GroupSeason.number.desc()).limit(1))

    async def history(self, group_id):
        return (await self.db.scalars(select(GroupSeason).where(GroupSeason.group_id == group_id, GroupSeason.archived_rankings.is_not(None)).order_by(GroupSeason.number.desc()))).all()
