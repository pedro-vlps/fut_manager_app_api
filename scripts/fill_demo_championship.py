"""Inscreve os quatro times da demonstração em uma edição existente, sem iniciá-la."""
import argparse
import asyncio
import json
from uuid import UUID, uuid5
from src.configs.db_connection import SessionLocal, engine
from src.models.entities import Profile
from src.models.championships import Championship, Club, ChampionshipEntry, ChampionshipPlayer
from src.services.championships import ChampionshipsService


async def main(championship_id):
    async with SessionLocal() as db:
        async with db.begin():
            service = ChampionshipsService(db)
            cup = await service.locked(Championship, championship_id)
            owner = await db.get(Profile, cup.owner_id) if cup else None
            if not cup or not owner or owner.email.lower() != 'email@email.com':
                raise RuntimeError('Campeonato de teste da conta solicitada não encontrado.')
            if cup.format != 'groups_knockout' or cup.capacity != 4 or cup.status != 'registration':
                raise RuntimeError('A edição precisa ser de grupos + mata-mata, com 4 vagas e inscrições abertas.')
            source = uuid5(owner.id, 'cascade-demo-2026-v1')
            expected = [uuid5(source, f'club:{seed}') for seed in range(1, 5)]
            existing = await service.entries(cup.id)
            if any(e.club_id not in expected for e, _ in existing):
                raise RuntimeError('Já existem outros times inscritos; nenhuma alteração realizada.')
            registered = {e.club_id for e, _ in existing}
            for club_id in expected:
                if club_id in registered:
                    continue
                club = await service.locked(Club, club_id)
                if club is None:
                    raise RuntimeError('Time de demonstração não encontrado.')
                players = [p for m, p in await service.members(club_id) if m.status == 'accepted' and p.is_active]
                if len(players) < 2:
                    raise RuntimeError('Elenco de demonstração incompleto.')
                entry = ChampionshipEntry(championship_id=cup.id, club_id=club_id, seed=len(registered) + 1)
                db.add(entry)
                await db.flush()
                for player in players:
                    db.add(ChampionshipPlayer(championship_id=cup.id, entry_id=entry.id, profile_id=player.id))
                await db.flush()
                registered.add(club_id)
            result = {'id': str(cup.id), 'name': cup.name, 'code': cup.code, 'status': cup.status,
                      'teams': [{'name': name, 'seed': e.seed} for e, name in await service.entries(cup.id)],
                      'players': len(await service.players(cup.id))}
        print(json.dumps(result, ensure_ascii=False))
    await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('championship_id', type=UUID)
    asyncio.run(main(parser.parse_args().championship_id))
