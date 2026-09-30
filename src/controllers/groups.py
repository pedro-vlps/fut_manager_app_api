from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import EventPresence, PeladaGroup, Profile
from src.models.enums import EventStatus, GroupRole, PresenceStatus, TeamPlayerRole
from src.schemas.presences import EventPresenceSchema
from src.schemas.events import PeladaEventSchema
from src.schemas.groups import PeladaGroupSchema
from src.schemas.groups import EventOverview, GroupOverview, Person, RankingEntry
from src.services.groups import GroupsService
from src.helpers.groups import registration_error


async def accessible_group(
    group_id: UUID, response: Response, profile: Profile, db: AsyncSession
):
    service = GroupsService(db)
    response.headers["Cache-Control"] = "no-store"
    group = await service.get(PeladaGroup, group_id)
    member = await service.active_membership(group_id, profile)
    if group is None or (group.created_by_id != profile.id and member is None):
        raise HTTPException(404, "Grupo não encontrado ou acesso indisponível.")
    return group


async def overview(group: PeladaGroup, profile: Profile, db: AsyncSession):
    service = GroupsService(db)
    now = datetime.now(timezone.utc)
    event = await service.current_event(group)
    membership = await service.active_membership(group.id, profile)
    result = GroupOverview(
        group=PeladaGroupSchema.model_validate(group), next_event=None,
        can_manage=group.created_by_id == profile.id or bool(
            membership and membership.role in {GroupRole.OWNER, GroupRole.ADMIN}
        ),
    )
    if event:
        presence = await service.profile_presence(event, profile)
        count = await service.confirmed_count(event)
        member = await service.active_member_id(group, profile)
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
            confirmed_players_count=await service.confirmed_count(event, TeamPlayerRole.PLAYER),
            confirmed_goalkeepers_count=await service.confirmed_count(event, TeamPlayerRole.GOALKEEPER),
            my_presence=(
                EventPresenceSchema.model_validate(presence) if presence else None
            ),
            can_confirm=not reason and (not already),
            can_change_role=not reason and already and event.min_confirmed_goalkeepers is not None,
            confirmation_message=reason,
        )
    return result


async def group_event(db: AsyncSession, group_id: UUID, event_id: UUID, lock=False):
    service = GroupsService(db)
    event = await service.event_by_group(group_id, event_id, lock)
    if event is None:
        raise HTTPException(404, "Evento não encontrado neste grupo.")
    return event


async def confirm(
    event_id: UUID, group: PeladaGroup, profile: Profile, db: AsyncSession,
    role: TeamPlayerRole = TeamPlayerRole.PLAYER,
):
    service = GroupsService(db)
    event = await group_event(db, group.id, event_id, lock=True)
    if event.status in [EventStatus.FINISHED, EventStatus.CANCELLED]:
        raise HTTPException(
            409, "Este evento está encerrado e é somente para consulta."
        )
    member = await service.active_member_id(group, profile)
    if member is None:
        raise HTTPException(403, "Somente membros ativos podem confirmar presença.")
    presence = await service.profile_presence(event, profile)
    if presence and presence.status in [
        PresenceStatus.CONFIRMED,
        PresenceStatus.WAITLIST,
    ] and presence.role == role:
        return EventPresenceSchema.model_validate(presence)
    now = datetime.now(timezone.utc)
    reason = registration_error(event, now)
    if reason:
        raise HTTPException(409, reason)
    if presence is None:
        presence = EventPresence(event_id=event.id, profile_id=profile.id)
    has_rebalance = await service.has_waitlist_trigger()
    separate = event.min_confirmed_goalkeepers is not None
    count = await service.confirmed_count(event, role if separate else None)
    capacity = event.max_confirmed_goalkeepers if separate and role == TeamPlayerRole.GOALKEEPER else event.max_confirmed_players
    presence.role = role
    presence.status = PresenceStatus.CONFIRMED
    presence.confirmed_at = now
    presence.waitlist_position = None
    if capacity is not None and count >= capacity:
        presence.status = PresenceStatus.WAITLIST
    service.add(presence)
    await service.flush()
    if has_rebalance:
        await service.rebalance_waitlist(event)
    elif presence.status == PresenceStatus.WAITLIST:
        queue = await service.waiting_presences(event)
        for item in queue:
            item.waitlist_position = None
        await service.flush()
        for position, item in enumerate(queue, 1):
            item.waitlist_position = position
        await service.flush()
    await service.refresh(presence)
    result = EventPresenceSchema.model_validate(presence)
    await service.commit()
    return result


async def confirmed(event_id: UUID, group: PeladaGroup, db: AsyncSession):
    service = GroupsService(db)
    await group_event(db, group.id, event_id)
    rows = await service.confirmed_people(event_id)
    return [
        Person(
            id=p.profile_id or p.guest_id,
            name=name or guest_name,
            is_guest=p.guest_id is not None,
            role=p.role.value,
        )
        for p, name, guest_name in rows
    ]


async def history(group: PeladaGroup, db: AsyncSession):
    service = GroupsService(db)
    return await service.event_history(group)


async def members(group: PeladaGroup, db: AsyncSession):
    service = GroupsService(db)
    rows = await service.active_members(group)
    people = {p.id: Person(id=p.id, name=p.name, role=role.value) for p, role in rows}
    owner = await service.get(Profile, group.created_by_id)
    if owner:
        people[owner.id] = Person(
            id=owner.id, name=owner.name, role=GroupRole.OWNER.value
        )
    return sorted(
        people.values(), key=lambda p: (p.role != "owner", p.name.casefold(), str(p.id))
    )


async def rankings(group: PeladaGroup, db: AsyncSession):
    from src.controllers.seasons import current_rankings
    return (await current_rankings(group, db)).rankings


async def event_rankings(event_id, group, db):
    from src.controllers.rankings import calculate_rankings
    await group_event(db, group.id, event_id)
    return await calculate_rankings(group, db, event_id=event_id)


async def member_profile(group, profile_id, db, viewer):
    from src.schemas.member_profile import MemberProfile
    from src.controllers.trophies import my_trophies
    from src.controllers.lifecycle_support import can_manage
    people = await GroupsService(db).active_members(group)
    profile = next((p for p, _ in people if p.id == profile_id), None)
    if profile is None and profile_id == group.created_by_id:
        profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(404, "Membro não encontrado neste grupo.")
    return MemberProfile(id=profile.id, name=profile.name, positions=profile.positions or {},
                         trophies=await my_trophies(profile, db),
                         can_rate=await can_manage(db, group, viewer))
