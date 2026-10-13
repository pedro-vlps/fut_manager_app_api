"""Recalcula os prêmios individuais das edições encerradas, mantendo títulos coletivos."""
import asyncio
from src.configs.db_connection import SessionLocal, engine
from src.controllers.championships import award_championship
from src.services.championships import ChampionshipsService
from src.models.championships import Championship


async def main():
    async with SessionLocal() as db:
        service = ChampionshipsService(db)
        for edition in await service.championships():
            if edition.status != 'finished':
                continue
            championship = await service.locked(Championship, edition.id)
            matches = await service.matches(championship.id)
            await award_championship(service, championship, matches[-1] if matches else None)
        await service.commit()
    await engine.dispose()
    print('Premiações de campeonatos reconciliadas.')


if __name__ == '__main__':
    asyncio.run(main())
