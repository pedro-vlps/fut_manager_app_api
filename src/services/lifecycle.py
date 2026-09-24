from sqlalchemy import delete, select
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
    Profile,
)
from src.models.enums import GroupRole, MembershipStatus, MatchStatus, PresenceStatus
from src.services.base import DatabaseService


class LifecycleService(DatabaseService):

    async def manager_membership(self, group, profile):
        return await self.db.scalar(
            select(GroupMember.id).where(
                GroupMember.group_id == group.id,
                GroupMember.profile_id == profile.id,
                GroupMember.status == MembershipStatus.ACTIVE,
                GroupMember.role.in_([GroupRole.OWNER, GroupRole.ADMIN]),
            )
        )

    async def confirmed_players(self, event_id):
        return (
            await self.db.scalars(
                select(EventPresence)
                .where(
                    EventPresence.event_id == event_id,
                    EventPresence.status == PresenceStatus.CONFIRMED,
                )
                .order_by(EventPresence.created_at, EventPresence.id)
            )
        ).all()

    async def event_teams(self, event_id):
        return (
            await self.db.scalars(
                select(EventTeam)
                .where(EventTeam.event_id == event_id)
                .order_by(EventTeam.draw_order, EventTeam.id)
            )
        ).all()

    async def event_people(self, event):
        return (
            await self.db.execute(
                select(EventPresence, Profile.name, GroupGuest.name)
                .outerjoin(Profile, Profile.id == EventPresence.profile_id)
                .outerjoin(GroupGuest, GroupGuest.id == EventPresence.guest_id)
                .where(EventPresence.event_id == event.id)
                .order_by(EventPresence.created_at, EventPresence.id)
            )
        ).all()

    async def event_players(self, event):
        return (
            await self.db.scalars(
                select(EventTeamPlayer)
                .join(EventTeam)
                .where(EventTeam.event_id == event.id)
                .order_by(EventTeamPlayer.created_at, EventTeamPlayer.id)
            )
        ).all()

    async def event_matches(self, event):
        return (
            await self.db.scalars(
                select(Match)
                .where(Match.event_id == event.id)
                .order_by(Match.sequence.desc())
            )
        ).all()

    async def event_scores(self, event):
        return (
            await self.db.scalars(
                select(MatchTeam)
                .join(Match)
                .where(Match.event_id == event.id)
                .order_by(MatchTeam.created_at, MatchTeam.id)
            )
        ).all()

    async def event_actions(self, event):
        return (
            await self.db.execute(
                select(GameAction, Profile.name, GroupGuest.name)
                .join(Match)
                .outerjoin(Profile, Profile.id == GameAction.player_id)
                .outerjoin(GroupGuest, GroupGuest.id == GameAction.guest_id)
                .where(Match.event_id == event.id)
                .order_by(GameAction.occurred_at, GameAction.created_at, GameAction.id)
            )
        ).all()

    async def waiting_team_ids(self, event):
        return (
            await self.db.scalars(
                select(EventTeamQueueEntry.team_id)
                .where(EventTeamQueueEntry.event_id == event.id)
                .order_by(EventTeamQueueEntry.position)
            )
        ).all()

    async def first_match_id(self, event):
        return await self.db.scalar(
            select(Match.id).where(Match.event_id == event.id).limit(1)
        )

    async def delete_event_queue(self, event):
        return await self.db.execute(
            delete(EventTeamQueueEntry).where(EventTeamQueueEntry.event_id == event.id)
        )

    async def delete_event_players(self, event):
        old_ids = select(EventTeam.id).where(EventTeam.event_id == event.id)
        return await self.db.execute(
            delete(EventTeamPlayer).where(EventTeamPlayer.team_id.in_(old_ids))
        )

    async def delete_event_teams(self, event):
        return await self.db.execute(
            delete(EventTeam).where(EventTeam.event_id == event.id)
        )

    async def roster_with_teams(self, event):
        return (
            await self.db.execute(
                select(
                    EventTeamPlayer.team_id,
                    EventTeamPlayer.profile_id,
                    EventTeamPlayer.guest_id,
                )
                .join(EventTeam)
                .where(EventTeam.event_id == event.id)
            )
        ).all()

    async def delete_queue(self, event_id):
        return await self.db.execute(
            delete(EventTeamQueueEntry).where(EventTeamQueueEntry.event_id == event_id)
        )

    async def players_for_teams(self, team_ids):
        return (
            await self.db.scalars(
                select(EventTeamPlayer).where(EventTeamPlayer.team_id.in_(team_ids))
            )
        ).all()

    async def roster_people(self, event):
        return (
            await self.db.execute(
                select(EventTeamPlayer.profile_id, EventTeamPlayer.guest_id)
                .join(EventTeam)
                .where(EventTeam.event_id == event.id)
            )
        ).all()

    async def match_in_event(self, event, match_id):
        return await self.db.scalar(
            select(Match).where(Match.id == match_id, Match.event_id == event.id)
        )

    async def match_scores(self, match_id):
        return (
            await self.db.scalars(
                select(MatchTeam).where(MatchTeam.match_id == match_id)
            )
        ).all()

    async def player_lineup(self, match_id, payload, person):
        return await self.db.scalar(
            select(MatchLineup).where(
                MatchLineup.match_id == match_id,
                MatchLineup.team_id == payload.team_id,
                MatchLineup.profile_id == person.profile_id,
                MatchLineup.guest_id == person.guest_id,
            )
        )

    async def active_match_id(self, event):
        return await self.db.scalar(
            select(Match.id).where(
                Match.event_id == event.id, Match.status == MatchStatus.IN_PROGRESS
            )
        )
