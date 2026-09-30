"""Concede troféus de temporadas arquivadas, sem duplicar premiações."""
import asyncio
from sqlalchemy import select, func
from src.configs.db_connection import SessionLocal, engine
from src.controllers.trophies import award_season
from src.models.entities import GroupSeason, PeladaGroup, SeasonTrophy


async def main():
    async with SessionLocal() as db, db.begin():
        rows = (await db.execute(select(GroupSeason, PeladaGroup)
            .join(PeladaGroup, PeladaGroup.id == GroupSeason.group_id)
            .where(GroupSeason.archived_rankings.is_not(None))
            .order_by(PeladaGroup.id, GroupSeason.number))).all()
        for season, group in rows:
            await award_season(db, group, season)
        print(f'Temporadas processadas: {len(rows)}')
        print(f'Troféus no banco: {await db.scalar(select(func.count()).select_from(SeasonTrophy))}')
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
