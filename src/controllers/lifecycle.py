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
    MatchLineup,
    PeladaEvent,
    PeladaGroup,
    Profile,
)
from src.models.enums import EventStatus, MatchResult, MatchStatus, TeamPlayerRole, PresenceStatus
from src.controllers.groups import group_event
from src.controllers.scheduling import schedule_next
from src.schemas.lifecycle import (
    ActionRequest,
    FinishRequest,
    KickoffRequest,
    PlayerSelection,
    TeamSelection,
    TeamsRequest,
    TimerRequest,
    TemporaryPlayerRequest,
)
from src.services.lifecycle import LifecycleService
from src.helpers.lifecycle import require_open, timer_elapsed
from src.controllers.draw import get_settings as draw_settings
from src.helpers.team_balance import balanced_teams
from src.services.team_balance import draw_features
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


async def add_temporary_player(match_id, payload: TemporaryPlayerRequest, event, db):
    service = LifecycleService(db)
    await active_match(db, event, match_id)
    scores = await score_rows(db, match_id)
    if payload.team_id not in {s.team_id for s in scores}:
        raise HTTPException(422, "Selecione um dos times que estão jogando.")
    person = await service.get(EventPresence, payload.presence_id)
    if person is None or person.event_id != event.id or person.status != PresenceStatus.CONFIRMED:
        raise HTTPException(422, "Selecione um jogador confirmado neste evento.")
    waiting = await service.waiting_team_ids(event)
    candidates = await service.players_for_teams(waiting)
    source = next((p for p in candidates if (p.profile_id, p.guest_id) == (person.profile_id, person.guest_id)), None)
    if source is None:
        raise HTTPException(422, "O jogador precisa pertencer a um time que está de fora.")
    outgoing_person = await service.get(EventPresence, payload.outgoing_presence_id)
    if outgoing_person is None or outgoing_person.event_id != event.id or outgoing_person.id == person.id:
        raise HTTPException(422, "Escolha quem ficará fora desta partida.")
    outgoing = await service.person_lineup(match_id, outgoing_person)
    if outgoing is None or outgoing.team_id != payload.team_id:
        raise HTTPException(422, "Quem sai precisa estar escalado no time selecionado.")
    existing = await service.person_lineup(match_id, person)
    if existing:
        if existing.team_id != payload.team_id or existing.replaced_lineup_id != outgoing.id or not existing.is_active:
            raise HTTPException(409, "Este jogador já participou de outra troca nesta partida. Atualize a tela.")
        return await save(db, event)
    if not outgoing.is_active:
        raise HTTPException(409, "Este jogador já está fora da partida. Atualize a tela.")
    if source.role != outgoing.role:
        raise HTTPException(422, "Escolha um substituto da mesma função: jogador de linha ou goleiro.")
    outgoing.is_active = False
    service.add(MatchLineup(match_id=match_id, team_id=payload.team_id,
        profile_id=person.profile_id, guest_id=person.guest_id, role=source.role,
        replaced_lineup_id=outgoing.id))
    return await save(db, event)


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
    separate = event.min_confirmed_goalkeepers is not None
    keepers = [p for p in players if p.role == TeamPlayerRole.GOALKEEPER]
    settings = None
    if payload.mode == "random":
        group = await service.get(PeladaGroup, event.group_id)
        settings = await draw_settings(db, group)
    if payload.mode == "random" and any(settings.model_dump().values()):
        field_count = sum(p.role == TeamPlayerRole.PLAYER for p in players) if separate else len(players)
        if field_count < payload.team_count:
            raise HTTPException(409, "É necessário pelo menos um jogador por time.")
        if separate and len(keepers) > payload.team_count:
            raise HTTPException(409, "Há mais goleiros que times. Ajuste as vagas ou a quantidade de times.")
        features = await draw_features(db, event, players, settings)
        rosters = balanced_teams(players, payload.team_count, features, settings, rng, separate)
        selections = []
        for index, roster in enumerate(rosters):
            # Em eventos antigos, mantém um goleiro por time. Se posições estão
            # ativas, prioriza quem informou essa preferência na modalidade.
            keeper = next((p for p in roster if "goleiro" in features[p.id]["positions"]), roster[0])
            selections.append(TeamSelection(name=f"Time {index + 1}", players=[
                PlayerSelection(presence_id=p.id, role=p.role if separate else
                                TeamPlayerRole.GOALKEEPER if p.id == keeper.id else TeamPlayerRole.PLAYER)
                for p in roster
            ]))
    elif payload.mode == "random" and separate:
        field_players = [p for p in players if p.role == TeamPlayerRole.PLAYER]
        if len(field_players) < payload.team_count:
            raise HTTPException(409, "É necessário pelo menos um jogador de linha por time.")
        if len(keepers) > payload.team_count:
            raise HTTPException(409, "Há mais goleiros que times. Ajuste as vagas ou a quantidade de times.")
        rng.shuffle(field_players)
        rng.shuffle(keepers)
        selections = [TeamSelection(name=f"Time {i + 1}", players=[
            PlayerSelection(presence_id=p.id, role=TeamPlayerRole.PLAYER)
            for p in field_players[i::payload.team_count]
        ] + ([PlayerSelection(presence_id=keepers[i].id, role=TeamPlayerRole.GOALKEEPER)]
             if i < len(keepers) else [])) for i in range(payload.team_count)]
    elif payload.mode == "random":
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
    if separate:
        if any(chosen.role != player_map[chosen.presence_id].role for team in selections for chosen in team.players):
            raise HTTPException(422, "Respeite a função escolhida na confirmação de presença.")
        if any(not any(p.role == TeamPlayerRole.PLAYER for p in team.players) for team in selections):
            raise HTTPException(422, "Cada time precisa de jogadores de linha.")
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
    confirmed = await confirmed_players(db, event.id)
    separate = event.min_confirmed_goalkeepers is not None
    count = sum(p.role == TeamPlayerRole.PLAYER for p in confirmed) if separate else len(confirmed)
    minimum = max(3, event.min_confirmed_players or 0)
    if count < minimum:
        raise HTTPException(409, f"É necessário ter {minimum} confirmados; há {count}.")
    if separate and sum(p.role == TeamPlayerRole.GOALKEEPER for p in confirmed) < event.min_confirmed_goalkeepers:
        raise HTTPException(409, f"É necessário ter {event.min_confirmed_goalkeepers} goleiros confirmados.")
    teams = await event_teams(db, event.id)
    roster = await service.roster_with_teams(event)
    if separate:
        expected_roles = {(p.profile_id, p.guest_id): p.role for p in confirmed}
        assigned = await service.event_players(event)
        if any(p.role != expected_roles.get((p.profile_id, p.guest_id)) for p in assigned):
            raise HTTPException(409, "As funções dos confirmados mudaram. Monte os times novamente.")
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
    if event.min_confirmed_goalkeepers is not None:
        keepers = [p for p in await service.event_players(event) if p.role == TeamPlayerRole.GOALKEEPER]
        if len(keepers) == 2:
            rng.shuffle(keepers)
            for keeper, team_id in zip(keepers, selected):
                keeper.team_id = team_id
            await service.flush()
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
        if event.min_confirmed_goalkeepers is not None:
            keepers = [p for p in await service.event_players(event) if p.role == TeamPlayerRole.GOALKEEPER]
            if len(keepers) == 2:
                for keeper in keepers:
                    if keeper.team_id == loser:
                        keeper.team_id = challenger
                await service.flush()
        await replace_queue(db, event.id, list(queue[1:]) + [loser])
        await create_match(
            db, event, [winner, challenger], match.sequence + 1, match.id
        )
    else:
        event.status = EventStatus.FINISHED
        event.finished_at = now
        await schedule_next(db, event)
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
    await schedule_next(db, event)
    await replace_queue(db, event.id, [])
    return await save(db, event)


async def update_modality(payload, event, db):
    if event.status == EventStatus.IN_PROGRESS:
        raise HTTPException(409, "A modalidade só pode ser alterada antes de iniciar o evento.")
    event.modality = payload.modality
    return await save(db, event)


async def update_confirmation_settings(payload, event, db):
    service = LifecycleService(db)
    if event.status == EventStatus.IN_PROGRESS or await service.first_match_id(event):
        raise HTTPException(409, "As vagas só podem ser alteradas antes de iniciar o evento.")
    for key, value in payload.model_dump().items():
        setattr(event, key, value)
    # A capacidade pode alterar os confirmados e tornar a formação anterior inválida.
    await service.delete_event_queue(event)
    await service.delete_event_players(event)
    await service.delete_event_teams(event)
    return await save(db, event)
