"""Cria uma edição de demonstração sem alterar contas ou reiniciar jogos existentes."""
import asyncio
import json
import secrets
from uuid import uuid5

from sqlalchemy import func, select
from src.configs.db_connection import SessionLocal, engine
from src.models.entities import Profile
from src.models.championships import Club, ClubMember, Championship, ChampionshipEntry, ChampionshipPlayer
from src.controllers.championships import detail


async def main():
    async with SessionLocal() as db:
        async with db.begin():
            owner = await db.scalar(select(Profile).where(func.lower(Profile.email) == "email@email.com").with_for_update())
            if owner is None or not owner.is_active:
                raise RuntimeError("A conta email@email.com precisa existir e estar ativa.")
            cup_id = uuid5(owner.id, "cascade-demo-2026-v1")
            cup = await db.get(Championship, cup_id)
            if cup is None:
                cup = Championship(id=cup_id, name="Copa Cascata · Teste", season="2026 · Demonstração",
                    description="Campeonato de teste com quatro times e elencos confirmados. Pronto para iniciar a cascata e testar resultados e troféus.",
                    owner_id=owner.id, format="cascade", capacity=4, status="registration")
                db.add(cup)
                await db.flush()
                for seed, (team_name, names) in enumerate([
                    ("Falcões FC", [None, "Lucas Demo", "Rafael Demo", "Bruno Demo"]),
                    ("Tigres FC", ["Diego Demo", "Felipe Demo", "Gustavo Demo", "Henrique Demo"]),
                    ("Lobos FC", ["Igor Demo", "João Demo", "Leandro Demo", "Marcos Demo"]),
                    ("Águias FC", ["Nicolas Demo", "Otávio Demo", "Paulo Demo", "Ricardo Demo"]),
                ], 1):
                    players = []
                    for position, name in enumerate(names, 1):
                        if name is None:
                            player = owner
                        else:
                            identifier = uuid5(cup_id, f"player:{seed}:{position}")
                            player = Profile(id=identifier, name=name,
                                email=f"cascata.{identifier.hex}@example.test",
                                password=secrets.token_urlsafe(32), is_active=True)
                            db.add(player)
                        players.append(player)
                    await db.flush()
                    club = Club(id=uuid5(cup_id, f"club:{seed}"), name=team_name, owner_id=players[0].id)
                    db.add(club)
                    await db.flush()
                    entry = ChampionshipEntry(id=uuid5(cup_id, f"entry:{seed}"), championship_id=cup.id, club_id=club.id, seed=seed)
                    db.add(entry)
                    await db.flush()
                    for player in players:
                        db.add(ClubMember(club_id=club.id, profile_id=player.id, status="accepted"))
                        db.add(ChampionshipPlayer(championship_id=cup.id, entry_id=entry.id, profile_id=player.id))
                await db.flush()
            result = await detail(cup.id, owner, db)
            assert result.owner_id == owner.id and result.format == "cascade" and result.capacity == 4
            assert len(result.entries) == 4 and all(len(entry.players) == 4 for entry in result.entries)
        print(json.dumps({"id": str(result.id), "name": result.name, "owner": owner.email,
            "status": result.status, "teams": [{"seed": e.seed, "name": e.name, "players": len(e.players)} for e in result.entries],
            "matches": len(result.matches)}, ensure_ascii=False))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
