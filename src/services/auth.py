from sqlalchemy import func, or_, select
from src.models.entities import GroupMember, PeladaGroup, Profile
from src.models.enums import MembershipStatus
from src.services.base import DatabaseService


class AuthService(DatabaseService):

    async def find_profile_id_by_email(self, email):
        return await self.db.scalar(
            select(Profile.id).where(func.lower(Profile.email) == email)
        )

    async def profiles_by_email(self, email: str):
        return (
            await self.db.scalars(
                select(Profile).where(func.lower(Profile.email) == email)
            )
        ).all()

    async def groups_for_profile(self, profile):
        membership = select(GroupMember.group_id).where(
            GroupMember.profile_id == profile.id,
            GroupMember.status == MembershipStatus.ACTIVE,
        )
        return (
            await self.db.execute(
                select(PeladaGroup, GroupMember.role)
                .outerjoin(
                    GroupMember,
                    (GroupMember.group_id == PeladaGroup.id)
                    & (GroupMember.profile_id == profile.id),
                )
                .where(
                    or_(
                        PeladaGroup.created_by_id == profile.id,
                        PeladaGroup.id.in_(membership),
                    )
                )
                .order_by(func.lower(PeladaGroup.name), PeladaGroup.id)
            )
        ).all()
