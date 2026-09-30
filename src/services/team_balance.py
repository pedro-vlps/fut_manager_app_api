from sqlalchemy import func, select
from src.models.entities import GroupPlayerRating, Match, MatchLineup, MatchTeam, PeladaEvent, Profile
from src.models.enums import EventStatus, MatchResult, MatchStatus
from src.schemas.player_positions import MODALITIES


async def draw_features(db, event, players, settings):
    profile_ids = [p.profile_id for p in players if p.profile_id]
    profiles = {}
    if settings.use_positions:
        profiles = {p.id: p for p in (await db.scalars(select(Profile).where(Profile.id.in_(profile_ids)))).all()}
    ratings = {}
    if settings.use_ratings:
        ratings = dict((await db.execute(select(GroupPlayerRating.profile_id, GroupPlayerRating.rating).where(
            GroupPlayerRating.group_id == event.group_id, GroupPlayerRating.profile_id.in_(profile_ids),
        ))).all())
    wins = {}
    if settings.use_wins:
        rows = (await db.execute(select(MatchLineup.profile_id, MatchLineup.guest_id, func.count())
            .join(Match, Match.id == MatchLineup.match_id)
            .join(PeladaEvent, PeladaEvent.id == Match.event_id)
            .join(MatchTeam, (MatchTeam.match_id == MatchLineup.match_id) & (MatchTeam.team_id == MatchLineup.team_id))
            .where(PeladaEvent.group_id == event.group_id, PeladaEvent.status != EventStatus.CANCELLED,
                   Match.status == MatchStatus.FINISHED, MatchTeam.result == MatchResult.WIN,
                   MatchLineup.is_active.is_(True))
            .group_by(MatchLineup.profile_id, MatchLineup.guest_id))).all()
        wins = {(profile_id, guest_id): count for profile_id, guest_id, count in rows}
    result = {}
    valid_positions = MODALITIES.get(event.modality, {}).get("positions", {})
    for player in players:
        profile = profiles.get(player.profile_id)
        preferred = set((profile.positions or {}).get(event.modality, [])) if profile else set()
        preferred.intersection_update(valid_positions)
        if event.min_confirmed_goalkeepers is not None:
            # A confirmação é soberana sobre preferências de posição do perfil.
            if player.role.value == "goalkeeper":
                preferred = {"goleiro"} if event.modality else set()
            else:
                preferred.discard("goleiro")
        result[player.id] = {
            "positions": preferred,
            "rating": int(ratings.get(player.profile_id, 5) * 10),
            "wins": wins.get((player.profile_id, player.guest_id), 0),
        }
    return result
