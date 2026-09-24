"""Popula um grupo existente com dados fictícios, sem sobrescrever registros.

Uso: FUT_MANAGER_DEMO_PASSWORD=... python -m scripts.seed_demo --group-id UUID --saturday 2026-09-26
IDs determinísticos permitem repetir o comando sem duplicar ou resetar testes.
"""

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from src.configs.db_connection import SessionLocal, engine
from src.models.entities import (
    EventPresence,
    EventTeam,
    EventTeamPlayer,
    GameAction,
    GroupGuest,
    GroupMember,
    Match,
    MatchLineup,
    MatchTeam,
    PeladaEvent,
    PeladaGroup,
    Profile,
)
from src.models.enums import (
    EventStatus,
    GameActionType,
    GroupRole,
    MembershipStatus,
    MatchResult,
    MatchStatus,
    PresenceStatus,
    TeamPlayerRole,
)


async def seed(group_id: UUID, saturday: date, password: str, start_now=False):
    if saturday.weekday() != 5:
        raise ValueError("A data do próximo evento precisa ser um sábado.")
    if len(password) < 8:
        raise ValueError("Informe uma senha de teste com pelo menos oito caracteres.")
    zone = ZoneInfo("America/Sao_Paulo")
    scheduled = datetime.combine(saturday, time(9), zone)
    counts = Counter()
    accounts = []
    async with SessionLocal() as db, db.begin():
        group = await db.scalar(
            select(PeladaGroup).where(PeladaGroup.id == group_id).with_for_update()
        )
        if group is None:
            raise ValueError("Grupo não encontrado. Nenhum dado foi criado.")

        def uid(key):
            return uuid5(group_id, f"futmanager-demo-v1:{key}")

        async def ensure(model, key, **values):
            item = await db.get(model, uid(key))
            if item is None:
                item = model(id=uid(key), **values)
                db.add(item)
                await db.flush()
                counts[model.__tablename__] += 1
            return item

        users = []
        for index, (slug, name) in enumerate(
            [
                ("bruno", "Bruno Costa"),
                ("carlos", "Carlos Lima"),
                ("diego", "Diego Santos"),
                ("eduardo", "Eduardo Alves"),
                ("felipe", "Felipe Rocha"),
                ("gabriel", "Gabriel Souza"),
                ("henrique", "Henrique Melo"),
                ("lucas", "Lucas Ribeiro"),
            ]
        ):
            email = f"{slug}.teste@futmanager.test"
            existing = await db.scalar(select(Profile).where(Profile.email == email))
            if existing and existing.id != uid(f"profile:{slug}"):
                raise ValueError(
                    f"O e-mail {email} já existe fora deste seed; nenhuma alteração será feita."
                )
            profile = await ensure(
                Profile,
                f"profile:{slug}",
                name=f"{name} (teste)",
                email=email,
                password=password,
                is_active=True,
                positions={
                    "campo": ["goleiro"] if index in (0, 4) else ["meia", "atacante"],
                    "futsal": ["goleiro"] if index in (0, 4) else ["ala_direita", "pivo"],
                    "fut7": ["goleiro"] if index in (0, 4) else ["meia", "pivo"],
                },
            )
            users.append(profile)
            await ensure(
                GroupMember,
                f"member:{slug}",
                group_id=group.id,
                profile_id=profile.id,
                role=GroupRole.ADMIN if index == 0 else GroupRole.MEMBER,
                status=MembershipStatus.ACTIVE,
            )
            accounts.append(
                {
                    "name": profile.name,
                    "email": email,
                    "role": "admin" if index == 0 else "member",
                }
            )

        guest = await ensure(
            GroupGuest,
            "guest:rafael",
            group_id=group.id,
            created_by_id=users[0].id,
            name="Rafael Convidado (teste)",
        )

        for week, scores in [(3, (3, 1)), (2, (2, 2)), (1, (1, 2))]:
            day = scheduled - timedelta(weeks=week)
            key = f"history:{day.date()}"
            event = await ensure(
                PeladaEvent,
                key,
                group_id=group.id,
                created_by_id=users[0].id,
                title=f"Pelada de teste • {day:%d/%m}",
                location="Arena Central — quadra society",
                scheduled_at=day,
                registration_opens_at=day - timedelta(days=6),
                registration_closes_at=day - timedelta(hours=1),
                min_confirmed_players=8,
                max_confirmed_players=8,
                match_duration_minutes=20,
                status=EventStatus.FINISHED,
                started_at=day,
                finished_at=day + timedelta(minutes=20),
            )
            for index, profile in enumerate(users):
                await ensure(
                    EventPresence,
                    f"{key}:presence:{index}",
                    event_id=event.id,
                    profile_id=profile.id,
                    status=PresenceStatus.CONFIRMED,
                    confirmed_at=day - timedelta(days=1),
                )
            teams = []
            for team_index, (name, color) in enumerate(
                [("Time Verde", "#176B49"), ("Time Azul", "#2563EB")]
            ):
                teams.append(
                    await ensure(
                        EventTeam,
                        f"{key}:team:{team_index}",
                        event_id=event.id,
                        name=name,
                        color=color,
                        draw_order=team_index + 1,
                    )
                )
            match = await ensure(
                Match,
                f"{key}:match",
                event_id=event.id,
                sequence=1,
                status=MatchStatus.FINISHED,
                started_at=day,
                ended_at=day + timedelta(minutes=20),
            )
            for index, profile in enumerate(users):
                team = teams[index // 4]
                role = (
                    TeamPlayerRole.GOALKEEPER
                    if index in (0, 4)
                    else TeamPlayerRole.PLAYER
                )
                await ensure(
                    EventTeamPlayer,
                    f"{key}:player:{index}",
                    team_id=team.id,
                    profile_id=profile.id,
                    role=role,
                )
                await ensure(
                    MatchLineup,
                    f"{key}:lineup:{index}",
                    match_id=match.id,
                    team_id=team.id,
                    profile_id=profile.id,
                    role=role,
                )
            for team_index, score in enumerate(scores):
                against = scores[1 - team_index]
                result = (
                    MatchResult.WIN
                    if score > against
                    else MatchResult.LOSS if score < against else MatchResult.DRAW
                )
                await ensure(
                    MatchTeam,
                    f"{key}:result:{team_index}",
                    match_id=match.id,
                    team_id=teams[team_index].id,
                    goals=score,
                    result=result,
                )
                for goal in range(score):
                    own_goal = week == 1 and team_index == 1 and goal == 1
                    player_index = 3 if own_goal else team_index * 4 + 1 + (goal % 3)
                    minute = 3 + goal * 5 + team_index
                    await ensure(
                        GameAction,
                        f"{key}:goal:{team_index}:{goal}",
                        match_id=match.id,
                        team_id=teams[player_index // 4].id,
                        player_id=users[player_index].id,
                        action_type=(
                            GameActionType.OWN_GOAL if own_goal else GameActionType.GOAL
                        ),
                        occurred_at=day + timedelta(minutes=minute),
                        minute=minute,
                    )
                    if not own_goal:
                        assist_index = team_index * 4 + 1 + ((goal + 1) % 3)
                        await ensure(
                            GameAction,
                            f"{key}:assist:{team_index}:{goal}",
                            match_id=match.id,
                            team_id=teams[team_index].id,
                            player_id=users[assist_index].id,
                            action_type=GameActionType.ASSIST,
                            occurred_at=day + timedelta(minutes=minute),
                            minute=minute,
                        )
            await ensure(
                GameAction,
                f"{key}:yellow",
                match_id=match.id,
                team_id=teams[0].id,
                player_id=users[2].id,
                action_type=GameActionType.YELLOW_CARD,
                occurred_at=day + timedelta(minutes=15),
                minute=15,
            )
            if week == 1:
                await ensure(
                    GameAction,
                    f"{key}:red",
                    match_id=match.id,
                    team_id=teams[1].id,
                    player_id=users[7].id,
                    action_type=GameActionType.RED_CARD,
                    occurred_at=day + timedelta(minutes=19),
                    minute=19,
                )

        key = f"upcoming:{saturday}"
        current_date = datetime.now(zone) if start_now else scheduled
        upcoming = await ensure(
            PeladaEvent,
            key,
            group_id=group.id,
            created_by_id=users[0].id,
            title=(
                "Pelada de teste • ciclo de partidas"
                if start_now
                else f"Pelada de sábado • {scheduled:%d/%m}"
            ),
            location="Arena Central — quadra society",
            scheduled_at=current_date,
            registration_opens_at=current_date - timedelta(days=7),
            registration_closes_at=(
                current_date if start_now else current_date - timedelta(minutes=30)
            ),
            min_confirmed_players=6,
            max_confirmed_players=8,
            match_duration_minutes=20,
            status=(
                EventStatus.REGISTRATION_CLOSED
                if start_now
                else EventStatus.REGISTRATION_OPEN
            ),
        )
        for index in ((0, 2, 3, 4, 5) if start_now else (2, 3, 4, 5)):
            await ensure(
                EventPresence,
                f"{key}:presence:{index}",
                event_id=upcoming.id,
                profile_id=users[index].id,
                status=PresenceStatus.CONFIRMED,
                confirmed_at=datetime.now(zone),
            )
        await ensure(
            EventPresence,
            f"{key}:guest",
            event_id=upcoming.id,
            guest_id=guest.id,
            status=PresenceStatus.CONFIRMED,
            confirmed_at=datetime.now(zone),
        )
        summary = {
            "group": group.name,
            "group_id": str(group.id),
            "upcoming_event_id": str(upcoming.id),
            "scheduled_at": upcoming.scheduled_at.isoformat(),
            "created": dict(counts),
            "accounts": accounts,
        }
    await engine.dispose()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True, type=UUID)
    parser.add_argument("--saturday", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--start-now",
        action="store_true",
        help="Cria o evento atual com seis confirmados e pronto para iniciar.",
    )
    args = parser.parse_args()
    password = os.environ.get("FUT_MANAGER_DEMO_PASSWORD", "")
    asyncio.run(seed(args.group_id, args.saturday, password, args.start_now))
