"""Cria uma liga local de demonstração e simula as 15 rodadas atomicamente.

Execute no ambiente da API: python scripts/simulate_demo_league.py --owner-email SEU_EMAIL_DE_TESTE
Use --home-and-away para criar 30 rodadas e deixar o returno pendente.
Pode repetir: reutiliza a mesma edição de demonstração já simulada.
"""
import argparse
import asyncio
import json
import random
from secrets import token_urlsafe
from uuid import uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.configs.db_connection import engine
from src.controllers import championships as controller
from src.models.championships import Championship, ClubMember
from src.models.entities import Profile
from src.schemas.championships import ChampionshipCreate, MatchActionInput, NamedInput, Registration, Score
from src.services.championships import ChampionshipsService

TEAMS = ['Santos', 'Palmeiras', 'Corinthians', 'São Paulo', 'Flamengo', 'Fluminense',
         'Vasco', 'Botafogo', 'Grêmio', 'Internacional', 'Cruzeiro', 'Atlético Mineiro',
         'Bahia', 'Fortaleza', 'Athletico Paranaense', 'Sport']


def summary(data):
    total_rounds = 30 if data.home_and_away else 15
    names = {entry.club_id: entry.name for entry in data.entries}
    rounds = []
    pairs = set()
    for round in range(1, total_rounds + 1):
        games = [m for m in data.matches if m.round == round]
        teams = [team for m in games for team in (m.home_id, m.away_id)]
        if len(games) != 8 or len(set(teams)) != 16 or any((m.home_score is not None) != (round <= 15) for m in games):
            raise RuntimeError(f'Rodada {round} incompleta ou com times repetidos.')
        pairs.update(frozenset((m.home_id, m.away_id)) for m in games)
        rounds.append({'round': round, 'finished_matches': sum(m.home_score is not None for m in games), 'pending_matches': sum(m.home_score is None for m in games)})
    expected_status = 'in_progress' if data.home_and_away else 'finished'
    if len(pairs) != 120 or len(data.matches) != total_rounds * 8 or data.status != expected_status or not data.statistics_complete:
        raise RuntimeError('A simulação não registrou as 15 primeiras rodadas com estatísticas completas.')
    if any(row.played != 15 or row.points != row.wins * 3 + row.draws for row in data.general_standings):
        raise RuntimeError('Classificação inconsistente.')
    if data.home_and_away:
        for first, second in zip(data.matches[:120], data.matches[120:]):
            if (second.round, second.home_id, second.away_id) != (first.round + 15, first.away_id, first.home_id):
                raise RuntimeError('Returno com mandos incorretos.')
        if data.champion_id is not None or data.trophies:
            raise RuntimeError('A liga não pode ser premiada antes do returno.')
    return dict(id=str(data.id), code=data.code, name=data.name, status=data.status,
                teams=len(data.entries), players=sum(len(e.players) for e in data.entries),
                home_and_away=data.home_and_away, matches=len(data.matches), finished_matches=120, pending_matches=sum(m.home_score is None for m in data.matches), rounds=rounds, trophies=len(data.trophies),
                champion=names.get(data.champion_id), leader=names[data.general_standings[0].club_id], runner_up=names[data.general_standings[1].club_id] if data.status == 'finished' else None,
                standings=[dict(position=i + 1, team=names[r.club_id], points=r.points,
                                played=r.played, wins=r.wins, draws=r.draws, losses=r.losses,
                                goals_for=r.goals_for, goals_against=r.goals_against)
                           for i, r in enumerate(data.general_standings)])


async def main(owner_email, home_and_away=False):
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                async with AsyncSession(bind=connection, expire_on_commit=False,
                                        join_transaction_mode='create_savepoint') as db:
                    service = ChampionshipsService(db)
                    owner = await service.profile_by_email(owner_email)
                    if owner is None:
                        raise RuntimeError('Conta ativa responsável pela demonstração não encontrada.')
                    namespace = uuid5(owner.id, 'league-home-away-demo-16-teams-2026-v1' if home_and_away else 'league-demo-16-teams-2026-v1')
                    # Serializa execuções para evitar criar times duplicados.
                    await db.execute(select(Profile).where(Profile.id == owner.id).with_for_update())
                    existing = await service.get(Championship, namespace)
                    if existing:
                        result = summary(await controller.detail(namespace, owner, db))
                    else:
                        payload = ChampionshipCreate(name='Liga Demo · Ida e volta · 16 times' if home_and_away else 'Liga Demo · 16 times', season='2026 · Simulação',
                            description='Demonstração com 16 times e as primeiras 15 rodadas simuladas. Dados fictícios.',
                            format='league', capacity=16, home_and_away=home_and_away)
                        cup = Championship(id=namespace, owner_id=owner.id, **payload.model_dump())
                        db.add(cup)
                        await db.flush()
                        for seed, name in enumerate(TEAMS, 1):
                            players = []
                            for number in (1, 2):
                                player = Profile(id=uuid5(namespace, f'player:{seed}:{number}'),
                                    name=f'{name} · Jogador {number} (demo)',
                                    email=f'liga-demo-{namespace.hex}-{seed}-{number}@example.test',
                                    password=token_urlsafe(32), positions={}, is_active=True)
                                db.add(player)
                                players.append(player)
                            await db.flush()
                            captain, teammate = players
                            club = await controller.create_club(NamedInput(name=f'{name} (demo)'), captain, db)
                            db.add(ClubMember(club_id=club.id, profile_id=teammate.id, status='accepted'))
                            await db.flush()
                            await controller.register(cup.id, Registration(club_id=club.id), captain, db)
                        data = await controller.start(cup.id, owner, db)
                        rosters = {entry.club_id: entry.players for entry in data.entries}
                        rng = random.Random(20261011)
                        # Começa na última rodada: confirma que não há bloqueio entre rodadas.
                        for round in range(15, 0, -1):
                            for match in [m for m in data.matches if m.round == round]:
                                scores = [rng.randrange(4), rng.randrange(4)]
                                actions = []
                                for team, goals in zip((match.home_id, match.away_id), scores):
                                    for goal in range(goals):
                                        scorer, assister = rosters[team][goal % 2], rosters[team][1 - goal % 2]
                                        for kind, player in [('goal', scorer), ('assist', assister)]:
                                            action = MatchActionInput(id=uuid4(), team_id=team,
                                                presence_id=player.id, action_type=kind)
                                            await controller.add_action(cup.id, match.id, action, owner, db)
                                            actions.append(action.id)
                                data = await controller.score(cup.id, match.id,
                                    Score(home_score=scores[0], away_score=scores[1], action_ids=actions), owner, db)
                            print(f'Rodada {round}: 8 jogos simulados.', flush=True)
                        result = summary(data)
            # Só informa sucesso depois do commit da transação externa.
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-email', required=True)
    parser.add_argument('--home-and-away', action='store_true', help='Cria 30 rodadas e simula somente as primeiras 15.')
    args = parser.parse_args()
    asyncio.run(main(args.owner_email, args.home_and_away))
