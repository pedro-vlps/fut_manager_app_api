from datetime import datetime, timezone
from random import SystemRandom
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import (
    EventPresence,
    EventTeam,
    EventTeamPlayer,
    GameAction,
    PeladaEvent,
    PeladaGroup,
    Profile,
)
from src.models.enums import EventStatus, MatchResult, MatchStatus, TeamPlayerRole
from src.controllers.groups import group_event
from src.schemas.lifecycle import (
    ActionRequest,
    FinishRequest,
    KickoffRequest,
    PlayerSelection,
    TeamSelection,
    TeamsRequest,
    TimerRequest,
)
from src.services.lifecycle import LifecycleService
from src.helpers.lifecycle import require_open, timer_elapsed
from src.controllers.lifecycle_support import (
    active_match,
    apply_score,
    can_manage,
    confirmed_players,
    create_match,
    event_teams,
    replace_queue,
    save,
    score_rows,
    snapshot,
)

rng = SystemRandom()
COLORS = ["#176B49", "#2563EB", "#B45309", "#9333EA", "#BE123C", "#0E7490"]


async def managed_event(
    event_id: UUID, group: PeladaGroup, profile: Profile, db: AsyncSession
):
    if not await can_manage(db, group, profile):
        raise HTTPException(
            403, "Somente organizadores e administradores podem gerenciar o evento."
        )
    event = await group_event(db, group.id, event_id, lock=True)
    require_open(event)
    return event


async def get_lifecycle(
    event_id: UUID, group: PeladaGroup, profile: Profile, db: AsyncSession
):
    event = await group_event(db, group.id, event_id)
    return await snapshot(db, event, await can_manage(db, group, profile))


async def build_teams(payload: TeamsRequest, event: PeladaEvent, db: AsyncSession):
    service = LifecycleService(db)
    require_open(event)
    if event.status == EventStatus.IN_PROGRESS:
        raise HTTPException(
            409, "Os times devem ser definidos antes de iniciar o evento."
        )
    if await service.first_match_id(event):
        raise HTTPException(409, "Os times não podem mudar depois da primeira partida.")
    players = await confirmed_players(db, event.id)
    player_map = {p.id: p for p in players}
    if payload.mode == "random":
        if len(players) < payload.team_count:
            raise HTTPException(409, "É necessário pelo menos um confirmado por time.")
        rng.shuffle(players)
        selections = [
            TeamSelection(
                name=f"Time {i + 1}",
                players=[
                    PlayerSelection(
                        presence_id=p.id,
                        role=(
                            TeamPlayerRole.GOALKEEPER
                            if j == 0
                            else TeamPlayerRole.PLAYER
                        ),
                    )
                    for j, p in enumerate(players[i :: payload.team_count])
                ],
            )
            for i in range(payload.team_count)
        ]
    else:
        selections = payload.teams
        if not 3 <= len(selections) <= 4:
            raise HTTPException(422, "Monte três ou quatro times para fazer o rodízio.")
    names = [s.name.strip() for s in selections]
    if any((not n for n in names)) or len(set((n.casefold() for n in names))) != len(
        names
    ):
        raise HTTPException(422, "Cada time precisa de um nome diferente.")
    assigned = [p.presence_id for team in selections for p in team.players]
    if len(set(assigned)) != len(assigned) or set(assigned) != set(player_map):
        raise HTTPException(
            422,
            "Distribua todos os confirmados uma única vez, sem incluir pessoas de fora.",
        )
    if any(
        (
            sum((p.role == TeamPlayerRole.GOALKEEPER for p in team.players)) > 1
            for team in selections
        )
    ):
        raise HTTPException(422, "Escolha no máximo um goleiro por time.")
    await service.delete_event_queue(event)
    await service.delete_event_players(event)
    await service.delete_event_teams(event)
    for index, selection in enumerate(selections):
        team = EventTeam(
            event_id=event.id,
            name=names[index],
            color=COLORS[index % len(COLORS)],
            draw_order=index + 1,
        )
        service.add(team)
        await service.flush()
        for chosen in selection.players:
            person = player_map[chosen.presence_id]
            service.add(
                EventTeamPlayer(
                    team_id=team.id,
                    profile_id=person.profile_id,
                    guest_id=person.guest_id,
                    role=chosen.role,
                )
            )
    return await save(db, event)


async def start(event: PeladaEvent, db: AsyncSession):
    service = LifecycleService(db)
    require_open(event)
    if event.status == EventStatus.IN_PROGRESS:
        return await snapshot(db, event, True)
    count = len(await confirmed_players(db, event.id))
    minimum = max(3, event.min_confirmed_players or 0)
    if count < minimum:
        raise HTTPException(409, f"É necessário ter {minimum} confirmados; há {count}.")
    teams = await event_teams(db, event.id)
    roster = await service.roster_with_teams(event)
    expected = {
        (p.profile_id, p.guest_id) for p in await confirmed_players(db, event.id)
    }
    if (
        not 3 <= len(teams) <= 4
        or {r.team_id for r in roster} != {t.id for t in teams}
        or len(roster) != len(expected)
        or ({(r.profile_id, r.guest_id) for r in roster} != expected)
    ):
        raise HTTPException(
            409,
            "Sorteie ou selecione todos os confirmados em três ou quatro times antes de iniciar.",
        )
    event.status = EventStatus.IN_PROGRESS
    event.started_at = datetime.now(timezone.utc)
    event.registration_closes_at = event.started_at
    return await save(db, event)


async def kickoff(payload: KickoffRequest, event: PeladaEvent, db: AsyncSession):
    service = LifecycleService(db)
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, "Inicie o evento antes de escolher o confronto.")
    if await service.first_match_id(event):
        raise HTTPException(409, "A primeira partida já foi criada. Atualize a tela.")
    teams = await event_teams(db, event.id)
    if len(teams) < 3:
        raise HTTPException(409, "Monte pelo menos três times antes de começar.")
    ids = [t.id for t in teams]
    if payload.mode == "random":
        rng.shuffle(ids)
        selected = ids[:2]
    else:
        selected = payload.team_ids
        if (
            len(selected) != 2
            or len(set(selected)) != 2
            or (not set(selected).issubset(ids))
        ):
            raise HTTPException(422, "Escolha dois times diferentes deste evento.")
    roster = await service.roster_people(event)
    expected = {
        (p.profile_id, p.guest_id) for p in await confirmed_players(db, event.id)
    }
    if len(roster) != len(expected) or set(roster) != expected:
        raise HTTPException(
            409, "A lista de confirmados mudou. Monte os times novamente."
        )
    await replace_queue(db, event.id, [i for i in ids if i not in selected])
    await create_match(db, event, selected, 1)
    return await save(db, event)


async def control_timer(
    match_id: UUID, payload: TimerRequest, event: PeladaEvent, db: AsyncSession
):
    match = await active_match(db, event, match_id)
    now = datetime.now(timezone.utc)
    if payload.action == "play" and match.timer_running_since is None:
        match.timer_running_since = now
    elif payload.action == "pause" and match.timer_running_since is not None:
        match.timer_elapsed_ms = timer_elapsed(match, now)
        match.timer_running_since = None
    return await save(db, event)


async def add_action(
    match_id: UUID, payload: ActionRequest, event: PeladaEvent, db: AsyncSession
):
    service = LifecycleService(db)
    await active_match(db, event, match_id)
    person = await service.get(EventPresence, payload.presence_id)
    if person is None or person.event_id != event.id:
        raise HTTPException(422, "Jogador não pertence a este evento.")
    lineup = await service.player_lineup(match_id, payload, person)
    if lineup is None:
        raise HTTPException(422, "Escolha um jogador escalado no time desta partida.")
    existing = await service.get(GameAction, payload.id)
    if existing:
        if (
            existing.match_id,
            existing.team_id,
            existing.player_id,
            existing.guest_id,
            existing.action_type,
            existing.minute,
        ) != (
            match_id,
            payload.team_id,
            person.profile_id,
            person.guest_id,
            payload.action_type,
            payload.minute,
        ):
            raise HTTPException(409, "Identificador de lançamento já utilizado.")
        return await snapshot(db, event, True)
    action = GameAction(
        id=payload.id,
        match_id=match_id,
        team_id=payload.team_id,
        player_id=person.profile_id,
        guest_id=person.guest_id,
        action_type=payload.action_type,
        minute=payload.minute,
        occurred_at=datetime.now(timezone.utc),
    )
    service.add(action)
    await apply_score(db, action, 1)
    return await save(db, event)


async def remove_action(
    match_id: UUID, action_id: UUID, event: PeladaEvent, db: AsyncSession
):
    service = LifecycleService(db)
    await active_match(db, event, match_id)
    action = await service.get(GameAction, action_id)
    if action is None:
        return await snapshot(db, event, True)
    if action.match_id != match_id:
        raise HTTPException(404, "Lançamento não encontrado nesta partida.")
    await apply_score(db, action, -1)
    await service.delete(action)
    return await save(db, event)


async def finish_match(
    match_id: UUID, payload: FinishRequest, event: PeladaEvent, db: AsyncSession
):
    service = LifecycleService(db)
    match = await active_match(db, event, match_id)
    scores = await score_rows(db, match.id)
    tied = scores[0].goals == scores[1].goals
    ids = [s.team_id for s in scores]
    if tied:
        if payload.random_tiebreak:
            winner = rng.choice(ids)
        elif payload.advancing_team_id in ids:
            winner = payload.advancing_team_id
        else:
            raise HTTPException(422, "Em empate, escolha ou sorteie o time que avança.")
    else:
        winner = max(scores, key=lambda s: s.goals).team_id
        if payload.random_tiebreak or (
            payload.advancing_team_id and payload.advancing_team_id != winner
        ):
            raise HTTPException(
                422,
                "O vencedor precisa corresponder ao placar. Corrija os lançamentos se necessário.",
            )
    loser = next((i for i in ids if i != winner))
    now = datetime.now(timezone.utc)
    match.timer_elapsed_ms = timer_elapsed(match, now)
    match.timer_running_since = None
    match.status = MatchStatus.FINISHED
    match.ended_at = now
    match.advancing_team_id = winner
    for score in scores:
        score.result = (
            MatchResult.DRAW
            if tied
            else MatchResult.WIN if score.team_id == winner else MatchResult.LOSS
        )
    if payload.continue_cycle:
        queue = await service.waiting_team_ids(event)
        if not queue or set(queue).intersection(ids):
            raise HTTPException(409, "Não há uma fila válida para a próxima partida.")
        challenger = queue[0]
        await replace_queue(db, event.id, list(queue[1:]) + [loser])
        await create_match(
            db, event, [winner, challenger], match.sequence + 1, match.id
        )
    else:
        event.status = EventStatus.FINISHED
        event.finished_at = now
        await replace_queue(db, event.id, [])
    return await save(db, event)


async def finish_event(event: PeladaEvent, db: AsyncSession):
    service = LifecycleService(db)
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, "O evento não está em andamento.")
    if await service.active_match_id(event):
        raise HTTPException(
            409, "Finalize a partida atual escolhendo encerrar o evento."
        )
    event.status = EventStatus.FINISHED
    event.finished_at = datetime.now(timezone.utc)
    await replace_queue(db, event.id, [])
    return await save(db, event)
