from sqlalchemy import select, or_
from sqlalchemy.dialects.postgresql import insert
from src.models.entities import SeasonTrophy, GroupSeason, GroupMember, PeladaGroup, PeladaEvent, Match, MatchLineup
from src.services.base import DatabaseService
from src.models.championships import ChampionshipTrophy


class TrophiesService(DatabaseService):
    async def championship_awards(self, profile_id):
        return (await self.db.scalars(select(ChampionshipTrophy).where(ChampionshipTrophy.profile_id == profile_id))).all()

    async def insert_awards(self, awards):
        if awards:
            await self.db.execute(insert(SeasonTrophy).values(awards).on_conflict_do_nothing(
                index_elements=["season_id", "profile_id", "category"]))

    async def profile_awards(self, profile_id):
        return (await self.db.scalars(select(SeasonTrophy).where(SeasonTrophy.profile_id == profile_id)
                .order_by(SeasonTrophy.awarded_at.desc(), SeasonTrophy.title, SeasonTrophy.id))).all()

    async def relevant_groups(self, profile_id):
        memberships = select(GroupMember.group_id).where(GroupMember.profile_id == profile_id)
        played = select(PeladaEvent.group_id).join(Match, Match.event_id == PeladaEvent.id).join(
            MatchLineup, MatchLineup.match_id == Match.id).where(MatchLineup.profile_id == profile_id)
        # A busca JSON no SQL não é compatível com snapshots cifrados. Resolve
        # a participação após a decifragem, sem comparar dados em texto no banco.
        snapshots = (await self.db.scalars(select(GroupSeason).where(GroupSeason.archived_rankings.is_not(None)))).all()
        archived = {season.group_id for season in snapshots if any(
            str(row.get('id')) == str(profile_id) and not row.get('is_guest', False)
            for row in (season.archived_rankings or []))}
        return (await self.db.scalars(select(PeladaGroup).where(or_(
            PeladaGroup.id.in_(memberships), PeladaGroup.id.in_(played), PeladaGroup.id.in_(archived)
        )).order_by(PeladaGroup.id))).all()

    async def archived_seasons(self, group_id):
        return (await self.db.scalars(select(GroupSeason).where(
            GroupSeason.group_id == group_id, GroupSeason.archived_rankings.is_not(None)))).all()
