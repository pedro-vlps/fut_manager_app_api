"""Área autenticada de um grupo: agenda, presenças, membros e estatísticas."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.configs.db_connection import get_db_session
from src.models.entities import (
    EventPresence,
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
    GroupRole,
    MembershipStatus,
    MatchStatus,
    PresenceStatus,
    TeamPlayerRole,
)
from src.routers.auth import current_profile
from src.schemas.crud import EventPresenceSchema, PeladaEventSchema, PeladaGroupSchema

router = APIRouter(prefix="/my-groups", tags=["Área do grupo"])


async def accessible_group(
    group_id: UUID,
    response: Response,
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    response.headers["Cache-Control"] = "no-store"
    group = await db.get(PeladaGroup, group_id)
    member = await db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.profile_id == profile.id,
            GroupMember.status == MembershipStatus.ACTIVE,
        )
    )
    if group is None or (group.created_by_id != profile.id and member is None):
        raise HTTPException(404, "Grupo não encontrado ou acesso indisponível.")
    return group


class EventOverview(PeladaEventSchema):
    confirmed_count: int
    my_presence: EventPresenceSchema | None
    can_confirm: bool
    confirmation_message: str | None


class GroupOverview(BaseModel):
    group: PeladaGroupSchema
    next_event: EventOverview | None


class Person(BaseModel):
    id: UUID
    name: str
    role: str | None = None
    is_guest: bool = False


class RankingEntry(Person):
    goals: int = 0
    own_goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    wins: int = 0
    losses: int = 0
    goals_conceded: int = 0
    matches: int = 0
    goalkeeper_matches: int = 0


def registration_error(event: PeladaEvent, now: datetime) -> str | None:
    if event.status != EventStatus.REGISTRATION_OPEN or event.scheduled_at <= now:
        return "As inscrições deste evento estão encerradas."
    if event.registration_opens_at and event.registration_opens_at > now:
        return "As inscrições deste evento ainda não abriram."
    if event.registration_closes_at and event.registration_closes_at <= now:
        return "O prazo para confirmar presença terminou."
    return None


@router.get("/{group_id}", response_model=GroupOverview)
async def overview(
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    now = datetime.now(timezone.utc)
    event = await db.scalar(
        select(PeladaEvent)
        .where(
            PeladaEvent.group_id == group.id,
            PeladaEvent.status.in_(
                [
                    EventStatus.REGISTRATION_OPEN,
                    EventStatus.REGISTRATION_CLOSED,
                    EventStatus.IN_PROGRESS,
                ]
            ),
        )
        .order_by(
            case((PeladaEvent.status == EventStatus.IN_PROGRESS, 0), else_=1),
            PeladaEvent.scheduled_at,
            PeladaEvent.id,
        )
        .limit(1)
    )
    result = GroupOverview(
        group=PeladaGroupSchema.model_validate(group), next_event=None
    )
    if event:
        presence = await db.scalar(
            select(EventPresence).where(
                EventPresence.event_id == event.id,
                EventPresence.profile_id == profile.id,
            )
        )
        count = await db.scalar(
            select(func.count())
            .select_from(EventPresence)
            .where(
                EventPresence.event_id == event.id,
                EventPresence.status == PresenceStatus.CONFIRMED,
            )
        )
        member = await db.scalar(
            select(GroupMember.id).where(
                GroupMember.group_id == group.id,
                GroupMember.profile_id == profile.id,
                GroupMember.status == MembershipStatus.ACTIVE,
            )
        )
        reason = registration_error(event, now)
        if member is None:
            reason = "Você precisa ser membro ativo para confirmar presença."
        already = presence is not None and presence.status in [
            PresenceStatus.CONFIRMED,
            PresenceStatus.WAITLIST,
        ]
        result.next_event = EventOverview(
            **PeladaEventSchema.model_validate(event).model_dump(),
            confirmed_count=count,
            my_presence=(
                EventPresenceSchema.model_validate(presence) if presence else None
            ),
            can_confirm=not reason and not already,
            confirmation_message=reason,
        )
    return result


async def group_event(db: AsyncSession, group_id: UUID, event_id: UUID, lock=False):
    query = select(PeladaEvent).where(
        PeladaEvent.id == event_id, PeladaEvent.group_id == group_id
    )
    if lock:
        query = query.with_for_update()
    event = await db.scalar(query)
    if event is None:
        raise HTTPException(404, "Evento não encontrado neste grupo.")
    return event


@router.post(
    "/{group_id}/events/{event_id}/confirm", response_model=EventPresenceSchema
)
async def confirm(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    # Serializa confirmações concorrentes e impede duplicidade ou excesso de vagas.
    event = await group_event(db, group.id, event_id, lock=True)
    if event.status in [EventStatus.FINISHED, EventStatus.CANCELLED]:
        raise HTTPException(
            409, "Este evento está encerrado e é somente para consulta."
        )
    member = await db.scalar(
        select(GroupMember.id).where(
            GroupMember.group_id == group.id,
            GroupMember.profile_id == profile.id,
            GroupMember.status == MembershipStatus.ACTIVE,
        )
    )
    if member is None:
        raise HTTPException(403, "Somente membros ativos podem confirmar presença.")
    presence = await db.scalar(
        select(EventPresence).where(
            EventPresence.event_id == event.id, EventPresence.profile_id == profile.id
        )
    )
    if presence and presence.status in [
        PresenceStatus.CONFIRMED,
        PresenceStatus.WAITLIST,
    ]:
        return EventPresenceSchema.model_validate(presence)
    now = datetime.now(timezone.utc)
    reason = registration_error(event, now)
    if reason:
        raise HTTPException(409, reason)
    if presence is None:
        presence = EventPresence(event_id=event.id, profile_id=profile.id)
    # Bancos migrados já fazem o rebalanceamento via trigger. Bancos novos,
    # criados com create_all, também precisam respeitar o limite e a prioridade.
    has_rebalance = await db.scalar(
        text("SELECT to_regprocedure('rebalance_event_waitlist(uuid)') IS NOT NULL")
    )
    count = await db.scalar(
        select(func.count())
        .select_from(EventPresence)
        .where(
            EventPresence.event_id == event.id,
            EventPresence.status == PresenceStatus.CONFIRMED,
        )
    )
    presence.status = PresenceStatus.CONFIRMED
    presence.confirmed_at = now
    presence.waitlist_position = None
    if event.max_confirmed_players is not None and count >= event.max_confirmed_players:
        presence.status = PresenceStatus.WAITLIST
    db.add(presence)
    await db.flush()
    if has_rebalance:
        await db.execute(
            text("SELECT rebalance_event_waitlist(:event_id)"), {"event_id": event.id}
        )
    elif presence.status == PresenceStatus.WAITLIST:
        queue = (
            await db.scalars(
                select(EventPresence)
                .where(
                    EventPresence.event_id == event.id,
                    EventPresence.status == PresenceStatus.WAITLIST,
                )
                .order_by(
                    EventPresence.guest_id.is_not(None),
                    EventPresence.waitlist_position.asc().nulls_last(),
                    EventPresence.created_at,
                    EventPresence.id,
                )
            )
        ).all()
        for item in queue:
            item.waitlist_position = None
        await db.flush()
        for position, item in enumerate(queue, 1):
            item.waitlist_position = position
        await db.flush()
    await db.refresh(presence)
    result = EventPresenceSchema.model_validate(presence)
    await db.commit()
    return result


@router.get("/{group_id}/events/{event_id}/confirmed", response_model=list[Person])
async def confirmed(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    await group_event(db, group.id, event_id)
    rows = (
        await db.execute(
            select(EventPresence, Profile.name, GroupGuest.name)
            .outerjoin(Profile, Profile.id == EventPresence.profile_id)
            .outerjoin(GroupGuest, GroupGuest.id == EventPresence.guest_id)
            .where(
                EventPresence.event_id == event_id,
                EventPresence.status == PresenceStatus.CONFIRMED,
            )
            .order_by(EventPresence.confirmed_at, EventPresence.id)
        )
    ).all()
    return [
        Person(
            id=p.profile_id or p.guest_id,
            name=name or guest_name,
            is_guest=p.guest_id is not None,
        )
        for p, name, guest_name in rows
    ]


@router.get("/{group_id}/history", response_model=list[PeladaEventSchema])
async def history(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    return (
        await db.scalars(
            select(PeladaEvent)
            .where(
                PeladaEvent.group_id == group.id,
                PeladaEvent.status.in_([EventStatus.FINISHED, EventStatus.CANCELLED]),
            )
            .order_by(PeladaEvent.scheduled_at.desc(), PeladaEvent.id)
        )
    ).all()


@router.get("/{group_id}/members", response_model=list[Person])
async def members(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    rows = (
        await db.execute(
            select(Profile, GroupMember.role)
            .join(GroupMember, GroupMember.profile_id == Profile.id)
            .where(
                GroupMember.group_id == group.id,
                GroupMember.status == MembershipStatus.ACTIVE,
            )
            .order_by(func.lower(Profile.name), Profile.id)
        )
    ).all()
    people = {p.id: Person(id=p.id, name=p.name, role=role.value) for p, role in rows}
    owner = await db.get(Profile, group.created_by_id)
    if owner:
        people[owner.id] = Person(
            id=owner.id, name=owner.name, role=GroupRole.OWNER.value
        )
    return sorted(
        people.values(), key=lambda p: (p.role != "owner", p.name.casefold(), str(p.id))
    )


@router.get("/{group_id}/rankings", response_model=list[RankingEntry])
async def rankings(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    entries = {}

    def entry(profile_id, guest_id, name, guest_name):
        key = ("guest" if guest_id else "profile", profile_id or guest_id)
        if key not in entries:
            entries[key] = RankingEntry(
                id=key[1], name=name or guest_name, is_guest=guest_id is not None
            )
        return entries[key]

    # Agrega ações separadamente dos resultados para não multiplicar os totais.
    actions = (
        await db.execute(
            select(
                GameAction.player_id,
                GameAction.guest_id,
                Profile.name,
                GroupGuest.name,
                GameAction.action_type,
                func.count(),
            )
            .join(Match, Match.id == GameAction.match_id)
            .join(PeladaEvent, PeladaEvent.id == Match.event_id)
            .outerjoin(Profile, Profile.id == GameAction.player_id)
            .outerjoin(GroupGuest, GroupGuest.id == GameAction.guest_id)
            .where(
                PeladaEvent.group_id == group.id,
                Match.status == MatchStatus.FINISHED,
                PeladaEvent.status != EventStatus.CANCELLED,
            )
            .group_by(
                GameAction.player_id,
                GameAction.guest_id,
                Profile.name,
                GroupGuest.name,
                GameAction.action_type,
            )
        )
    ).all()
    fields = {
        "goal": "goals",
        "own_goal": "own_goals",
        "assist": "assists",
        "yellow_card": "yellow_cards",
        "red_card": "red_cards",
    }
    for player, guest, name, guest_name, action, count in actions:
        person = entry(player, guest, name, guest_name)
        setattr(person, fields[action.value], count)
    opponent = aliased(MatchTeam)
    conceded = (
        select(func.coalesce(func.sum(opponent.goals), 0))
        .where(
            opponent.match_id == MatchLineup.match_id,
            opponent.team_id != MatchLineup.team_id,
        )
        .correlate(MatchLineup)
        .scalar_subquery()
    )
    lineups = (
        await db.execute(
            select(
                MatchLineup, Profile.name, GroupGuest.name, MatchTeam.result, conceded
            )
            .join(Match, Match.id == MatchLineup.match_id)
            .join(PeladaEvent, PeladaEvent.id == Match.event_id)
            .outerjoin(
                MatchTeam,
                (MatchTeam.match_id == MatchLineup.match_id)
                & (MatchTeam.team_id == MatchLineup.team_id),
            )
            .outerjoin(Profile, Profile.id == MatchLineup.profile_id)
            .outerjoin(GroupGuest, GroupGuest.id == MatchLineup.guest_id)
            .where(
                PeladaEvent.group_id == group.id,
                Match.status == MatchStatus.FINISHED,
                PeladaEvent.status != EventStatus.CANCELLED,
            )
        )
    ).all()
    for lineup, name, guest_name, result, goals in lineups:
        person = entry(lineup.profile_id, lineup.guest_id, name, guest_name)
        person.matches += 1
        person.wins += int(result == "win")
        person.losses += int(result == "loss")
        if lineup.role == TeamPlayerRole.GOALKEEPER:
            person.goals_conceded += goals
            person.goalkeeper_matches += 1
    return sorted(
        entries.values(), key=lambda p: (-p.goals, p.name.casefold(), str(p.id))
    )
