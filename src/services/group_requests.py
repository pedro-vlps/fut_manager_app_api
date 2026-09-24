from sqlalchemy import select
from src.models.entities import GroupJoinRequest, GroupMember, PeladaGroup, Profile
from src.services.base import DatabaseService


class GroupRequestsService(DatabaseService):
    async def by_code(self, code):
        return await self.db.scalar(select(PeladaGroup).where(PeladaGroup.code == code))

    async def locked_group(self, group_id):
        return await self.db.scalar(select(PeladaGroup).where(PeladaGroup.id == group_id).with_for_update())

    async def membership(self, group_id, profile_id):
        return await self.db.scalar(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.profile_id == profile_id))

    async def existing_request(self, group_id, profile_id):
        return await self.db.scalar(select(GroupJoinRequest).where(GroupJoinRequest.group_id == group_id, GroupJoinRequest.profile_id == profile_id))

    async def pending_requests(self, group_id):
        return (await self.db.execute(
            select(GroupJoinRequest, Profile.name).join(Profile, Profile.id == GroupJoinRequest.profile_id)
            .where(GroupJoinRequest.group_id == group_id, GroupJoinRequest.status == "pending")
            .order_by(GroupJoinRequest.created_at, GroupJoinRequest.id)
        )).all()
