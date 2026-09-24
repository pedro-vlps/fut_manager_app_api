from sqlalchemy import case, func, select, text
from sqlalchemy.orm import aliased
from src.models.entities import (
    EventPresence,
    GameAction,
    GroupGuest,
    GroupMember,
    Match,
    MatchLineup,
    MatchTeam,
    PeladaEvent,
    Profile,
)
from src.models.enums import EventStatus, MembershipStatus, MatchStatus, PresenceStatus
from src.services.base import DatabaseService


class GroupsService(DatabaseService):

    async def event_by_group(self, group_id, event_id, lock=False):
        query = select(PeladaEvent).where(
            PeladaEvent.id == event_id, PeladaEvent.group_id == group_id
        )
        if lock:
            query = query.with_for_update()
        return await self.db.scalar(query)

    async def active_membership(self, group_id, profile):
        return await self.db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.profile_id == profile.id,
                GroupMember.status == MembershipStatus.ACTIVE,
            )
        )

    async def current_event(self, group):
        return await self.db.scalar(
            select(PeladaEvent)
            .where(
                PeladaEvent.group_id == group.id,
                PeladaEvent.status.in_(
                    [
                        EventStatus.REGISTRATION_OPEN,
                        EventStatus.REGISTRATION_CLOSED,
                        EventStatus.IN_PROGRESS,
                    ]
                ),
            )
            .order_by(
                case((PeladaEvent.status == EventStatus.IN_PROGRESS, 0), else_=1),
                PeladaEvent.scheduled_at,
                PeladaEvent.id,
            )
            .limit(1)
        )

    async def profile_presence(self, event, profile):
        return await self.db.scalar(
            select(EventPresence).where(
                EventPresence.event_id == event.id,
                EventPresence.profile_id == profile.id,
            )
        )

    async def confirmed_count(self, event):
        return await self.db.scalar(
            select(func.count())
            .select_from(EventPresence)
            .where(
                EventPresence.event_id == event.id,
                EventPresence.status == PresenceStatus.CONFIRMED,
            )
        )

    async def active_member_id(self, group, profile):
        return await self.db.scalar(
            select(GroupMember.id).where(
                GroupMember.group_id == group.id,
                GroupMember.profile_id == profile.id,
                GroupMember.status == MembershipStatus.ACTIVE,
            )
        )

    async def has_waitlist_trigger(self):
        return await self.db.scalar(
            text("SELECT to_regprocedure('rebalance_event_waitlist(uuid)') IS NOT NULL")
        )

    async def rebalance_waitlist(self, event):
        return await self.db.execute(
            text("SELECT rebalance_event_waitlist(:event_id)"), {"event_id": event.id}
        )

    async def waiting_presences(self, event):
        return (
            await self.db.scalars(
                select(EventPresence)
                .where(
                    EventPresence.event_id == event.id,
                    EventPresence.status == PresenceStatus.WAITLIST,
                )
                .order_by(
                    EventPresence.guest_id.is_not(None),
                    EventPresence.waitlist_position.asc().nulls_last(),
                    EventPresence.created_at,
                    EventPresence.id,
                )
            )
        ).all()

    async def confirmed_people(self, event_id):
        return (
            await self.db.execute(
                select(EventPresence, Profile.name, GroupGuest.name)
                .outerjoin(Profile, Profile.id == EventPresence.profile_id)
                .outerjoin(GroupGuest, GroupGuest.id == EventPresence.guest_id)
                .where(
                    EventPresence.event_id == event_id,
                    EventPresence.status == PresenceStatus.CONFIRMED,
                )
                .order_by(EventPresence.confirmed_at, EventPresence.id)
            )
        ).all()

    async def event_history(self, group):
        return (
            await self.db.scalars(
                select(PeladaEvent)
                .where(
                    PeladaEvent.group_id == group.id,
                    PeladaEvent.status.in_(
                        [EventStatus.FINISHED, EventStatus.CANCELLED]
                    ),
                )
                .order_by(PeladaEvent.scheduled_at.desc(), PeladaEvent.id)
            )
        ).all()

    async def active_members(self, group):
        return (
            await self.db.execute(
                select(Profile, GroupMember.role)
                .join(GroupMember, GroupMember.profile_id == Profile.id)
                .where(
                    GroupMember.group_id == group.id,
                    GroupMember.status == MembershipStatus.ACTIVE,
                )
                .order_by(func.lower(Profile.name), Profile.id)
            )
        ).all()

    async def action_totals(self, group):
        return (
            await self.db.execute(
                select(
                    GameAction.player_id,
                    GameAction.guest_id,
                    Profile.name,
                    GroupGuest.name,
                    GameAction.action_type,
                    func.count(),
                )
                .join(Match, Match.id == GameAction.match_id)
                .join(PeladaEvent, PeladaEvent.id == Match.event_id)
                .outerjoin(Profile, Profile.id == GameAction.player_id)
                .outerjoin(GroupGuest, GroupGuest.id == GameAction.guest_id)
                .where(
                    PeladaEvent.group_id == group.id,
                    Match.status == MatchStatus.FINISHED,
                    PeladaEvent.status != EventStatus.CANCELLED,
                )
                .group_by(
                    GameAction.player_id,
                    GameAction.guest_id,
                    Profile.name,
                    GroupGuest.name,
                    GameAction.action_type,
                )
            )
        ).all()

    async def finished_lineups(self, group):
        opponent = aliased(MatchTeam)
        conceded = (
            select(func.coalesce(func.sum(opponent.goals), 0))
            .where(
                opponent.match_id == MatchLineup.match_id,
                opponent.team_id != MatchLineup.team_id,
            )
            .correlate(MatchLineup)
            .scalar_subquery()
        )
        return (
            await self.db.execute(
                select(
                    MatchLineup,
                    Profile.name,
                    GroupGuest.name,
                    MatchTeam.result,
                    conceded,
                )
                .join(Match, Match.id == MatchLineup.match_id)
                .join(PeladaEvent, PeladaEvent.id == Match.event_id)
                .outerjoin(
                    MatchTeam,
                    (MatchTeam.match_id == MatchLineup.match_id)
                    & (MatchTeam.team_id == MatchLineup.team_id),
                )
                .outerjoin(Profile, Profile.id == MatchLineup.profile_id)
                .outerjoin(GroupGuest, GroupGuest.id == MatchLineup.guest_id)
                .where(
                    PeladaEvent.group_id == group.id,
                    Match.status == MatchStatus.FINISHED,
                    PeladaEvent.status != EventStatus.CANCELLED,
                )
            )
        ).all()
