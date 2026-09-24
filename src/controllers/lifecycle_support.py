from datetime import datetime, timezone
from fastapi import HTTPException
from src.models.entities import EventTeamQueueEntry, Match, MatchLineup, MatchTeam
from src.models.enums import EventStatus, GameActionType, MatchStatus, PresenceStatus
from src.schemas.events import PeladaEventSchema
from src.schemas.lifecycle import (
    ActionView,
    LifecycleView,
    MatchView,
    Participant,
    ScoreView,
    TeamView,
)
from src.services.lifecycle import LifecycleService
from src.helpers.lifecycle import timer_elapsed


async def can_manage(db, group, profile):
    service = LifecycleService(db)
    if group.created_by_id == profile.id:
        return True
    return bool(await service.manager_membership(group, profile))


async def confirmed_players(db, event_id):
    service = LifecycleService(db)
    return await service.confirmed_players(event_id)


async def event_teams(db, event_id):
    service = LifecycleService(db)
    return await service.event_teams(event_id)


async def snapshot(db, event, manager):
    service = LifecycleService(db)
    people = await service.event_people(event)
    person_map = {}
    participants = []
    for p, name, guest_name in people:
        person = Participant(
            presence_id=p.id,
            person_id=p.profile_id or p.guest_id,
            name=name or guest_name,
            is_guest=p.guest_id is not None,
        )
        person_map[p.profile_id, p.guest_id] = person
        if p.status == PresenceStatus.CONFIRMED:
            participants.append(person)
    teams = await event_teams(db, event.id)
    team_names = {t.id: t.name for t in teams}
    players = await service.event_players(event)
    team_views = [
        TeamView(
            id=t.id,
            name=t.name,
            color=t.color,
            players=[
                person_map[p.profile_id, p.guest_id].model_copy(update={"role": p.role})
                for p in players
                if p.team_id == t.id and (p.profile_id, p.guest_id) in person_map
            ],
        )
        for t in teams
    ]
    matches = await service.event_matches(event)
    scores = await service.event_scores(event)
    actions = await service.event_actions(event)
    now = datetime.now(timezone.utc)
    views = [
        MatchView(
            id=m.id,
            sequence=m.sequence,
            status=m.status,
            advancing_team_id=m.advancing_team_id,
            timer_elapsed_ms=timer_elapsed(m, now),
            timer_running=m.timer_running_since is not None
            and m.status == MatchStatus.IN_PROGRESS,
            scores=[
                ScoreView(
                    team_id=s.team_id,
                    name=team_names.get(s.team_id, "Time"),
                    goals=s.goals,
                    result=s.result,
                )
                for s in scores
                if s.match_id == m.id
            ],
            actions=[
                ActionView(
                    id=a.id,
                    team_id=a.team_id,
                    player_name=name or guest_name,
                    action_type=a.action_type,
                    minute=a.minute,
                )
                for a, name, guest_name in actions
                if a.match_id == m.id
            ],
        )
        for m in matches
    ]
    waiting = await service.waiting_team_ids(event)
    return LifecycleView(
        event=PeladaEventSchema.model_validate(event),
        can_manage=manager
        and event.status not in [EventStatus.FINISHED, EventStatus.CANCELLED],
        participants=participants,
        teams=team_views,
        waiting_team_ids=waiting,
        current_match=next(
            (m for m in views if m.status == MatchStatus.IN_PROGRESS), None
        ),
        matches=views,
    )


async def save(db, event):
    service = LifecycleService(db)
    await service.flush()
    await service.refresh(event)
    result = await snapshot(db, event, True)
    await service.commit()
    return result


async def replace_queue(db, event_id, ids):
    service = LifecycleService(db)
    await service.delete_queue(event_id)
    for position, team_id in enumerate(ids, 1):
        service.add(
            EventTeamQueueEntry(event_id=event_id, team_id=team_id, position=position)
        )
    await service.flush()


async def create_match(db, event, team_ids, sequence, previous=None):
    service = LifecycleService(db)
    match = Match(
        event_id=event.id,
        sequence=sequence,
        previous_match_id=previous,
        status=MatchStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    service.add(match)
    await service.flush()
    players = await service.players_for_teams(team_ids)
    confirmed = {
        (p.profile_id, p.guest_id) for p in await confirmed_players(db, event.id)
    }
    if not players or any(
        ((p.profile_id, p.guest_id) not in confirmed for p in players)
    ):
        raise HTTPException(
            409,
            "Os times contêm jogadores sem presença confirmada. Revise a escalação.",
        )
    for team_id in team_ids:
        service.add(MatchTeam(match_id=match.id, team_id=team_id, goals=0))
    for p in players:
        service.add(
            MatchLineup(
                match_id=match.id,
                team_id=p.team_id,
                profile_id=p.profile_id,
                guest_id=p.guest_id,
                role=p.role,
            )
        )
    await service.flush()
    return match


async def active_match(db, event, match_id):
    service = LifecycleService(db)
    if event.status != EventStatus.IN_PROGRESS:
        raise HTTPException(409, "O evento não está em andamento.")
    match = await service.match_in_event(event, match_id)
    if match is None:
        raise HTTPException(404, "Partida não encontrada neste evento.")
    if match.status != MatchStatus.IN_PROGRESS:
        raise HTTPException(409, "Esta partida já terminou. Atualize a tela.")
    return match


async def score_rows(db, match_id):
    service = LifecycleService(db)
    rows = await service.match_scores(match_id)
    if len(rows) != 2:
        raise HTTPException(409, "A partida precisa ter exatamente dois times.")
    return rows


async def apply_score(db, action, delta):
    if action.action_type not in [GameActionType.GOAL, GameActionType.OWN_GOAL]:
        return
    scores = await score_rows(db, action.match_id)
    target = next(
        (
            s
            for s in scores
            if (s.team_id == action.team_id)
            == (action.action_type == GameActionType.GOAL)
        ),
        None,
    )
    if target is None or target.goals + delta < 0:
        raise HTTPException(409, "Placar inconsistente com os lançamentos.")
    target.goals += delta
