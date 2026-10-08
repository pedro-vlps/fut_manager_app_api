from sqlalchemy import select, func, or_
from sqlalchemy.dialects.postgresql import insert
from src.models.entities import Profile
from src.models.championships import Club, ClubMember, Championship, ChampionshipEntry, ChampionshipPlayer, ChampionshipMatch, ChampionshipStatistic, ChampionshipTrophy
from src.services.base import DatabaseService


class ChampionshipsService(DatabaseService):
    async def by_code(self, code):
        return await self.db.scalar(select(Championship).where(Championship.code == code))

    async def registered_profile(self, championship_id, club_id, profile_id):
        return await self.db.scalar(select(Profile)
            .join(ChampionshipPlayer, ChampionshipPlayer.profile_id == Profile.id)
            .join(ChampionshipEntry, ChampionshipEntry.id == ChampionshipPlayer.entry_id)
            .where(ChampionshipPlayer.championship_id == championship_id,
                   ChampionshipEntry.championship_id == championship_id,
                   ChampionshipEntry.club_id == club_id, Profile.id == profile_id))

    async def statistics(self, championship_id):
        return (await self.db.scalars(select(ChampionshipStatistic).join(ChampionshipMatch,
            ChampionshipMatch.id == ChampionshipStatistic.match_id)
            .where(ChampionshipMatch.championship_id == championship_id))).all()

    async def awards(self, championship_id):
        return (await self.db.execute(select(ChampionshipTrophy, Profile.name)
            .join(Profile, Profile.id == ChampionshipTrophy.profile_id)
            .where(ChampionshipTrophy.championship_id == championship_id)
            .order_by(ChampionshipTrophy.category, Profile.name, Profile.id))).all()

    async def insert_awards(self, awards):
        if awards:
            await self.db.execute(insert(ChampionshipTrophy).values(awards).on_conflict_do_nothing(
                index_elements=["championship_id", "profile_id", "category"]))

    async def locked(self, model, identifier):
        return await self.db.scalar(select(model).where(model.id == identifier).with_for_update())

    async def clubs(self, profile_id):
        return (await self.db.scalars(select(Club).where(or_(Club.owner_id == profile_id,
            Club.id.in_(select(ClubMember.club_id).where(ClubMember.profile_id == profile_id, ClubMember.status == "accepted"))))
            .order_by(Club.created_at, Club.id))).all()

    async def members(self, club_id):
        return (await self.db.execute(select(ClubMember, Profile).join(Profile, Profile.id == ClubMember.profile_id)
            .where(ClubMember.club_id == club_id).order_by(Profile.name, Profile.id))).all()

    async def member(self, club_id, profile_id):
        return await self.db.scalar(select(ClubMember).where(ClubMember.club_id == club_id, ClubMember.profile_id == profile_id))

    async def profile_by_email(self, email):
        return await self.db.scalar(select(Profile).where(func.lower(Profile.email) == email.lower(), Profile.is_active.is_(True)))

    async def invitations(self, profile_id):
        return (await self.db.execute(select(ClubMember, Club.name).join(Club, Club.id == ClubMember.club_id)
            .where(ClubMember.profile_id == profile_id, ClubMember.status == "pending"))).all()

    async def championships(self):
        return (await self.db.scalars(select(Championship).order_by(Championship.created_at.desc(), Championship.id))).all()

    async def entries(self, championship_id):
        return (await self.db.execute(select(ChampionshipEntry, Club.name).join(Club, Club.id == ChampionshipEntry.club_id)
            .where(ChampionshipEntry.championship_id == championship_id).order_by(ChampionshipEntry.seed))).all()

    async def players(self, championship_id):
        return (await self.db.execute(select(ChampionshipPlayer, Profile.name).join(Profile, Profile.id == ChampionshipPlayer.profile_id)
            .where(ChampionshipPlayer.championship_id == championship_id).order_by(Profile.name))).all()

    async def matches(self, championship_id):
        return (await self.db.scalars(select(ChampionshipMatch).where(ChampionshipMatch.championship_id == championship_id)
            .order_by(ChampionshipMatch.sequence))).all()
