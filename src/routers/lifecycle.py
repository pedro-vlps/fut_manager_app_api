"""Transições atômicas de evento, fila de times e partidas."""
from datetime import datetime, timezone
from random import SystemRandom
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.configs.db_connection import get_db_session
from src.models.entities import (EventPresence, EventTeam, EventTeamPlayer, EventTeamQueueEntry,
    GameAction, GroupGuest, GroupMember, Match, MatchLineup, MatchTeam, PeladaEvent, PeladaGroup, Profile)
from src.models.enums import (EventStatus, GameActionType, GroupRole, MembershipStatus,
    MatchResult, MatchStatus, PresenceStatus, TeamPlayerRole)
from src.routers.auth import current_profile
from src.routers.groups import accessible_group, group_event
from src.schemas.crud import PeladaEventSchema
from src.schemas.lifecycle import (ActionRequest, ActionView, FinishRequest, KickoffRequest,
    LifecycleView, MatchView, Participant, PlayerSelection, ScoreView, TeamSelection, TeamsRequest, TeamView, TimerRequest)

router = APIRouter(prefix='/my-groups/{group_id}/events/{event_id}', tags=['Ciclo do evento'])
rng = SystemRandom()
COLORS = ['#176B49', '#2563EB', '#B45309', '#9333EA', '#BE123C', '#0E7490']

async def can_manage(db, group, profile):
    if group.created_by_id == profile.id:
        return True
    return bool(await db.scalar(select(GroupMember.id).where(GroupMember.group_id == group.id,
        GroupMember.profile_id == profile.id, GroupMember.status == MembershipStatus.ACTIVE,
        GroupMember.role.in_([GroupRole.OWNER, GroupRole.ADMIN]))))

async def managed_event(event_id: UUID, group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    if not await can_manage(db, group, profile):
        raise HTTPException(403, 'Somente organizadores e administradores podem gerenciar o evento.')
    event = await group_event(db, group.id, event_id, lock=True)
    require_open(event)
    return event

async def confirmed_players(db, event_id):
    return (await db.scalars(select(EventPresence).where(EventPresence.event_id == event_id,
        EventPresence.status == PresenceStatus.CONFIRMED).order_by(EventPresence.created_at, EventPresence.id))).all()

async def event_teams(db, event_id):
    return (await db.scalars(select(EventTeam).where(EventTeam.event_id == event_id)
        .order_by(EventTeam.draw_order, EventTeam.id))).all()

async def snapshot(db, event, manager):
    people = (await db.execute(select(EventPresence, Profile.name, GroupGuest.name)
        .outerjoin(Profile, Profile.id == EventPresence.profile_id)
        .outerjoin(GroupGuest, GroupGuest.id == EventPresence.guest_id)
        .where(EventPresence.event_id == event.id).order_by(EventPresence.created_at, EventPresence.id))).all()
    person_map = {}
    participants = []
    for p, name, guest_name in people:
        person = Participant(presence_id=p.id, person_id=p.profile_id or p.guest_id,
            name=name or guest_name, is_guest=p.guest_id is not None)
        person_map[(p.profile_id, p.guest_id)] = person
        if p.status == PresenceStatus.CONFIRMED:
            participants.append(person)
    teams = await event_teams(db, event.id)
    team_names = {t.id:t.name for t in teams}
    players = (await db.scalars(select(EventTeamPlayer).join(EventTeam)
        .where(EventTeam.event_id == event.id).order_by(EventTeamPlayer.created_at, EventTeamPlayer.id))).all()
    team_views = [TeamView(id=t.id, name=t.name, color=t.color,
        players=[person_map[(p.profile_id,p.guest_id)].model_copy(update={'role':p.role})
            for p in players if p.team_id == t.id and (p.profile_id,p.guest_id) in person_map]) for t in teams]
    matches = (await db.scalars(select(Match).where(Match.event_id == event.id).order_by(Match.sequence.desc()))).all()
    scores = (await db.scalars(select(MatchTeam).join(Match).where(Match.event_id == event.id)
        .order_by(MatchTeam.created_at, MatchTeam.id))).all()
    actions = (await db.execute(select(GameAction, Profile.name, GroupGuest.name).join(Match)
        .outerjoin(Profile, Profile.id == GameAction.player_id).outerjoin(GroupGuest, GroupGuest.id == GameAction.guest_id)
        .where(Match.event_id == event.id).order_by(GameAction.occurred_at, GameAction.created_at, GameAction.id))).all()
    now = datetime.now(timezone.utc)
    views = [MatchView(id=m.id, sequence=m.sequence, status=m.status, advancing_team_id=m.advancing_team_id,
        timer_elapsed_ms=timer_elapsed(m, now), timer_running=m.timer_running_since is not None and m.status == MatchStatus.IN_PROGRESS,
        scores=[ScoreView(team_id=s.team_id, name=team_names.get(s.team_id, 'Time'), goals=s.goals, result=s.result)
            for s in scores if s.match_id == m.id],
        actions=[ActionView(id=a.id, team_id=a.team_id, player_name=name or guest_name,
            action_type=a.action_type, minute=a.minute) for a,name,guest_name in actions if a.match_id == m.id]) for m in matches]
    waiting = (await db.scalars(select(EventTeamQueueEntry.team_id).where(EventTeamQueueEntry.event_id == event.id)
        .order_by(EventTeamQueueEntry.position))).all()
    return LifecycleView(event=PeladaEventSchema.model_validate(event),
        can_manage=manager and event.status not in [EventStatus.FINISHED, EventStatus.CANCELLED],
        participants=participants, teams=team_views, waiting_team_ids=waiting,
        current_match=next((m for m in views if m.status == MatchStatus.IN_PROGRESS), None), matches=views)

async def save(db, event):
    await db.flush()
    await db.refresh(event)
    result = await snapshot(db, event, True)
    await db.commit()
    return result

def require_open(event):
    if event.status in [EventStatus.FINISHED, EventStatus.CANCELLED]:
        raise HTTPException(409, 'Este evento já foi encerrado ou cancelado.')

@router.get('/lifecycle', response_model=LifecycleView)
async def get_lifecycle(event_id: UUID, group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    event = await group_event(db, group.id, event_id)
    return await snapshot(db, event, await can_manage(db, group, profile))

@router.post('/teams', response_model=LifecycleView)
async def build_teams(payload: TeamsRequest, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
    require_open(event)
    if event.status == EventStatus.IN_PROGRESS:
        raise HTTPException(409, 'Os times devem ser definidos antes de iniciar o evento.')
    if await db.scalar(select(Match.id).where(Match.event_id == event.id).limit(1)):
        raise HTTPException(409, 'Os times não podem mudar depois da primeira partida.')
    players = await confirmed_players(db, event.id)
    player_map = {p.id:p for p in players}
    if payload.mode == 'random':
        if len(players) < payload.team_count:
            raise HTTPException(409, 'É necessário pelo menos um confirmado por time.')
        rng.shuffle(players)
        selections = [TeamSelection(name=f'Time {i+1}', players=[PlayerSelection(presence_id=p.id,
            role=TeamPlayerRole.GOALKEEPER if j == 0 else TeamPlayerRole.PLAYER)
            for j,p in enumerate(players[i::payload.team_count])]) for i in range(payload.team_count)]
    else:
        selections = payload.teams
        if not 3 <= len(selections) <= 4:
            raise HTTPException(422, 'Monte três ou quatro times para fazer o rodízio.')
    names = [s.name.strip() for s in selections]
    if any(not n for n in names) or len(set(n.casefold() for n in names)) != len(names):
        raise HTTPException(422, 'Cada time precisa de um nome diferente.')
    assigned = [p.presence_id for team in selections for p in team.players]
    if len(set(assigned)) != len(assigned) or set(assigned) != set(player_map):
        raise HTTPException(422, 'Distribua todos os confirmados uma única vez, sem incluir pessoas de fora.')
    if any(sum(p.role == TeamPlayerRole.GOALKEEPER for p in team.players) > 1 for team in selections):
        raise HTTPException(422, 'Escolha no máximo um goleiro por time.')
    old_ids = select(EventTeam.id).where(EventTeam.event_id == event.id)
    await db.execute(delete(EventTeamQueueEntry).where(EventTeamQueueEntry.event_id == event.id))
    await db.execute(delete(EventTeamPlayer).where(EventTeamPlayer.team_id.in_(old_ids)))
    await db.execute(delete(EventTeam).where(EventTeam.event_id == event.id))
    for index, selection in enumerate(selections):
        team = EventTeam(event_id=event.id, name=names[index], color=COLORS[index % len(COLORS)], draw_order=index+1)
        db.add(team)
        await db.flush()
        for chosen in selection.players:
            person = player_map[chosen.presence_id]
            db.add(EventTeamPlayer(team_id=team.id, profile_id=person.profile_id,
                guest_id=person.guest_id, role=chosen.role))
    return await save(db, event)

@router.post('/start', response_model=LifecycleView)
async def start(event: PeladaEvent = Depends(managed_event), db: AsyncSession = Depends(get_db_session)):
    require_open(event)
    if event.status == EventStatus.IN_PROGRESS:
        return await snapshot(db, event, True)
    count = len(await confirmed_players(db, event.id))
    minimum = max(3, event.min_confirmed_players or 0)
    if count < minimum:
        raise HTTPException(409, f'É necessário ter {minimum} confirmados; há {count}.')
    teams = await event_teams(db, event.id)
    roster = (await db.execute(select(EventTeamPlayer.team_id, EventTeamPlayer.profile_id, EventTeamPlayer.guest_id)
        .join(EventTeam).where(EventTeam.event_id == event.id))).all()
    expected = {(p.profile_id, p.guest_id) for p in await confirmed_players(db, event.id)}
    if (not 3 <= len(teams) <= 4 or {r.team_id for r in roster} != {t.id for t in teams}
        or len(roster) != len(expected) or {(r.profile_id, r.guest_id) for r in roster} != expected):
        raise HTTPException(409, 'Sorteie ou selecione todos os confirmados em três ou quatro times antes de iniciar.')
    event.status = EventStatus.IN_PROGRESS
    event.started_at = datetime.now(timezone.utc)
    event.registration_closes_at = event.started_at
    return await save(db, event)

async def replace_queue(db, event_id, ids):
    await db.execute(delete(EventTeamQueueEntry).where(EventTeamQueueEntry.event_id == event_id))
    for position, team_id in enumerate(ids, 1):
        db.add(EventTeamQueueEntry(event_id=event_id, team_id=team_id, position=position))
    await db.flush()

async def create_match(db, event, team_ids, sequence, previous=None):
    match = Match(event_id=event.id, sequence=sequence, previous_match_id=previous,
        status=MatchStatus.IN_PROGRESS, started_at=datetime.now(timezone.utc))
    db.add(match)
    await db.flush()
    players = (await db.scalars(select(EventTeamPlayer).where(EventTeamPlayer.team_id.in_(team_ids)))).all()
    confirmed = {(p.profile_id,p.guest_id) for p in await confirmed_players(db, event.id)}
    if not players or any((p.profile_id,p.guest_id) not in confirmed for p in players):
        raise HTTPException(409, 'Os times contêm jogadores sem presença confirmada. Revise a escalação.')
    for team_id in team_ids:
        db.add(MatchTeam(match_id=match.id, team_id=team_id, goals=0))
    for p in players:
        db.add(MatchLineup(match_id=match.id, team_id=p.team_id, profile_id=p.profile_id, guest_id=p.guest_id, role=p.role))
    await db.flush()
    return match

@router.post('/kickoff', response_model=LifecycleView)
async def kickoff(payload: KickoffRequest, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, 'Inicie o evento antes de escolher o confronto.')
    if await db.scalar(select(Match.id).where(Match.event_id == event.id).limit(1)):
        raise HTTPException(409, 'A primeira partida já foi criada. Atualize a tela.')
    teams = await event_teams(db, event.id)
    if len(teams) < 3:
        raise HTTPException(409, 'Monte pelo menos três times antes de começar.')
    ids = [t.id for t in teams]
    if payload.mode == 'random':
        rng.shuffle(ids)
        selected = ids[:2]
    else:
        selected = payload.team_ids
        if len(selected) != 2 or len(set(selected)) != 2 or not set(selected).issubset(ids):
            raise HTTPException(422, 'Escolha dois times diferentes deste evento.')
    # Se a lista de confirmados mudou após montar os times, não deixa ninguém de fora.
    roster = (await db.execute(select(EventTeamPlayer.profile_id, EventTeamPlayer.guest_id)
        .join(EventTeam).where(EventTeam.event_id == event.id))).all()
    expected = {(p.profile_id,p.guest_id) for p in await confirmed_players(db, event.id)}
    if len(roster) != len(expected) or set(roster) != expected:
        raise HTTPException(409, 'A lista de confirmados mudou. Monte os times novamente.')
    await replace_queue(db, event.id, [i for i in ids if i not in selected])
    await create_match(db, event, selected, 1)
    return await save(db, event)

async def active_match(db, event, match_id):
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, 'O evento não está em andamento.')
    match = await db.scalar(select(Match).where(Match.id == match_id, Match.event_id == event.id))
    if match is None:
        raise HTTPException(404, 'Partida não encontrada neste evento.')
    if match.status != MatchStatus.IN_PROGRESS:
        raise HTTPException(409, 'Esta partida já terminou. Atualize a tela.')
    return match

async def score_rows(db, match_id):
    rows = (await db.scalars(select(MatchTeam).where(MatchTeam.match_id == match_id))).all()
    if len(rows) != 2:
        raise HTTPException(409, 'A partida precisa ter exatamente dois times.')
    return rows

def timer_elapsed(match, now):
    elapsed = match.timer_elapsed_ms or 0
    if match.timer_running_since is not None:
        end = match.ended_at if match.status == MatchStatus.FINISHED and match.ended_at else now
        elapsed += max(0, int((end - match.timer_running_since).total_seconds() * 1000))
    return elapsed

@router.post('/matches/{match_id}/timer', response_model=LifecycleView)
async def control_timer(match_id: UUID, payload: TimerRequest, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
    match = await active_match(db, event, match_id)
    now = datetime.now(timezone.utc)
    if payload.action == 'play' and match.timer_running_since is None:
        match.timer_running_since = now
    elif payload.action == 'pause' and match.timer_running_since is not None:
        match.timer_elapsed_ms = timer_elapsed(match, now)
        match.timer_running_since = None
    return await save(db, event)

async def apply_score(db, action, delta):
    if action.action_type not in [GameActionType.GOAL, GameActionType.OWN_GOAL]:
        return
    scores = await score_rows(db, action.match_id)
    target = next((s for s in scores if (s.team_id == action.team_id) == (action.action_type == GameActionType.GOAL)), None)
    if target is None or target.goals + delta < 0:
        raise HTTPException(409, 'Placar inconsistente com os lançamentos.')
    target.goals += delta

@router.post('/matches/{match_id}/actions', response_model=LifecycleView)
async def add_action(match_id: UUID, payload: ActionRequest, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
    await active_match(db, event, match_id)
    person = await db.get(EventPresence, payload.presence_id)
    if person is None or person.event_id != event.id:
        raise HTTPException(422, 'Jogador não pertence a este evento.')
    lineup = await db.scalar(select(MatchLineup).where(MatchLineup.match_id == match_id,
        MatchLineup.team_id == payload.team_id, MatchLineup.profile_id == person.profile_id,
        MatchLineup.guest_id == person.guest_id))
    if lineup is None:
        raise HTTPException(422, 'Escolha um jogador escalado no time desta partida.')
    existing = await db.get(GameAction, payload.id)
    if existing:
        if (existing.match_id,existing.team_id,existing.player_id,existing.guest_id,existing.action_type,existing.minute) != (
            match_id,payload.team_id,person.profile_id,person.guest_id,payload.action_type,payload.minute):
            raise HTTPException(409, 'Identificador de lançamento já utilizado.')
        return await snapshot(db, event, True)
    action = GameAction(id=payload.id, match_id=match_id, team_id=payload.team_id,
        player_id=person.profile_id, guest_id=person.guest_id, action_type=payload.action_type,
        minute=payload.minute, occurred_at=datetime.now(timezone.utc))
    db.add(action)
    await apply_score(db, action, 1)
    return await save(db, event)

@router.post('/matches/{match_id}/actions/{action_id}/remove', response_model=LifecycleView)
async def remove_action(match_id: UUID, action_id: UUID, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
    await active_match(db, event, match_id)
    action = await db.get(GameAction, action_id)
    if action is None:
        return await snapshot(db, event, True)
    if action.match_id != match_id:
        raise HTTPException(404, 'Lançamento não encontrado nesta partida.')
    await apply_score(db, action, -1)
    await db.delete(action)
    return await save(db, event)

@router.post('/matches/{match_id}/finish', response_model=LifecycleView)
async def finish_match(match_id: UUID, payload: FinishRequest, event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session)):
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
            raise HTTPException(422, 'Em empate, escolha ou sorteie o time que avança.')
    else:
        winner = max(scores, key=lambda s:s.goals).team_id
        if payload.random_tiebreak or (payload.advancing_team_id and payload.advancing_team_id != winner):
            raise HTTPException(422, 'O vencedor precisa corresponder ao placar. Corrija os lançamentos se necessário.')
    loser = next(i for i in ids if i != winner)
    now = datetime.now(timezone.utc)
    match.timer_elapsed_ms = timer_elapsed(match, now)
    match.timer_running_since = None
    match.status = MatchStatus.FINISHED
    match.ended_at = now
    match.advancing_team_id = winner
    for score in scores:
        score.result = MatchResult.DRAW if tied else MatchResult.WIN if score.team_id == winner else MatchResult.LOSS
    if payload.continue_cycle:
        queue = (await db.scalars(select(EventTeamQueueEntry.team_id).where(EventTeamQueueEntry.event_id == event.id)
            .order_by(EventTeamQueueEntry.position))).all()
        if not queue or set(queue).intersection(ids):
            raise HTTPException(409, 'Não há uma fila válida para a próxima partida.')
        challenger = queue[0]
        await replace_queue(db, event.id, list(queue[1:]) + [loser])
        await create_match(db, event, [winner, challenger], match.sequence+1, match.id)
    else:
        event.status = EventStatus.FINISHED
        event.finished_at = now
        await replace_queue(db, event.id, [])
    return await save(db, event)

@router.post('/finish', response_model=LifecycleView)
async def finish_event(event: PeladaEvent = Depends(managed_event), db: AsyncSession = Depends(get_db_session)):
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, 'O evento não está em andamento.')
    if await db.scalar(select(Match.id).where(Match.event_id == event.id, Match.status == MatchStatus.IN_PROGRESS)):
        raise HTTPException(409, 'Finalize a partida atual escolhendo encerrar o evento.')
    event.status = EventStatus.FINISHED
    event.finished_at = datetime.now(timezone.utc)
    await replace_queue(db, event.id, [])
    return await save(db, event)
