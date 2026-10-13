from sqlalchemy import select
from src.models.entities import GroupMember, GroupPlayerRating, PeladaGroup
from src.models.enums import MembershipStatus
from src.services.base import DatabaseService


class DrawService(DatabaseService):
    async def lock_group(self, group_id):
        return await self.db.scalar(select(PeladaGroup).where(PeladaGroup.id == group_id).with_for_update())

    async def active_member_id(self, group_id, profile_id):
        return await self.db.scalar(select(GroupMember.id).where(GroupMember.group_id == group_id,
            GroupMember.profile_id == profile_id, GroupMember.status == MembershipStatus.ACTIVE))

    async def rating(self, group_id, profile_id):
        return await self.db.scalar(select(GroupPlayerRating).where(GroupPlayerRating.group_id == group_id,
            GroupPlayerRating.profile_id == profile_id))

    async def ratings(self, group_id, profile_ids):
        return dict((await self.db.execute(select(GroupPlayerRating.profile_id, GroupPlayerRating.rating).where(
            GroupPlayerRating.group_id == group_id, GroupPlayerRating.profile_id.in_(profile_ids)))).all())
