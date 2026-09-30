from collections import Counter
from uuid import UUID
from src.helpers.trophies import CATEGORIES, season_winners
from src.services.trophies import TrophiesService
from src.schemas.trophies import TrophyCollection, TrophyCount, TrophySchema


async def award_season(db, group, season):
    if season.archived_rankings is None:
        return
    awards = [{"season_id": season.id, "profile_id": UUID(str(profile_id)),
               "category": category, "value": value, "awarded_at": season.ends_at,
               "title": f"{CATEGORIES[category]} - Temporada {season.number} - {group.name}"}
              for category, profile_id, value in season_winners(season.archived_rankings)]
    await TrophiesService(db).insert_awards(awards)


async def my_trophies(profile, db):
    from src.controllers.seasons import synchronize
    from src.services.seasons import SeasonsService

    service = TrophiesService(db)
    for group in await service.relevant_groups(profile.id):
        # Reconcilia viradas mesmo quando o primeiro acesso é ao perfil.
        await synchronize(SeasonsService(db), group.id)
        for season in await service.archived_seasons(group.id):
            await award_season(db, group, season)
    trophies = [TrophySchema.model_validate(row) for row in await service.profile_awards(profile.id)]
    counts = Counter(row.category for row in trophies)
    result = TrophyCollection(total=len(trophies), trophies=trophies,
        summary=[TrophyCount(category=key, name=name, count=counts[key])
                 for key, name in CATEGORIES.items() if counts[key]])
    await service.commit()
    return result
