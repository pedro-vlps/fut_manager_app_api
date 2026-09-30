from fastapi import HTTPException
from sqlalchemy import select
from src.controllers.lifecycle_support import can_manage
from src.models.entities import GroupDrawSettings, GroupMember, GroupPlayerRating, PeladaGroup, Profile
from src.models.enums import MembershipStatus
from src.schemas.draw import DrawSettings, RatingView


async def require_manager(db, group, profile):
    if not await can_manage(db, group, profile):
        raise HTTPException(403, "Somente owners e administradores podem gerenciar avaliações e parâmetros de sorteio.")


async def get_settings(db, group):
    settings = await db.get(GroupDrawSettings, group.id)
    return DrawSettings.model_validate(settings) if settings else DrawSettings()


async def update_settings(db, group, profile, payload):
    await require_manager(db, group, profile)
    await db.scalar(select(PeladaGroup).where(PeladaGroup.id == group.id).with_for_update())
    settings = await db.get(GroupDrawSettings, group.id)
    if settings is None:
        settings = GroupDrawSettings(group_id=group.id)
        db.add(settings)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    await db.commit()
    return DrawSettings.model_validate(settings)


async def rating_target(db, group, profile, profile_id):
    await require_manager(db, group, profile)
    target = await db.get(Profile, profile_id)
    membership = await db.scalar(select(GroupMember.id).where(
        GroupMember.group_id == group.id, GroupMember.profile_id == profile_id,
        GroupMember.status == MembershipStatus.ACTIVE,
    ))
    if target is None or (group.created_by_id != profile_id and membership is None):
        raise HTTPException(404, "Jogador não encontrado neste grupo.")


async def get_rating(db, group, profile, profile_id):
    await rating_target(db, group, profile, profile_id)
    record = await db.scalar(select(GroupPlayerRating).where(
        GroupPlayerRating.group_id == group.id, GroupPlayerRating.profile_id == profile_id,
    ))
    return RatingView(rating=float(record.rating) if record else None)


async def update_rating(db, group, profile, profile_id, payload):
    await rating_target(db, group, profile, profile_id)
    # Serializa criação/remoção e evita duas avaliações para o mesmo vínculo.
    await db.scalar(select(PeladaGroup).where(PeladaGroup.id == group.id).with_for_update())
    record = await db.scalar(select(GroupPlayerRating).where(
        GroupPlayerRating.group_id == group.id, GroupPlayerRating.profile_id == profile_id,
    ))
    if payload.rating is None:
        if record:
            await db.delete(record)
    elif record:
        record.rating = payload.rating
        record.updated_by_id = profile.id
    else:
        db.add(GroupPlayerRating(group_id=group.id, profile_id=profile_id,
                                rating=payload.rating, updated_by_id=profile.id))
    await db.commit()
    return RatingView(rating=float(payload.rating) if payload.rating is not None else None)


async def team_ratings(db, group, profile, event_id):
    from src.controllers.groups import group_event
    from src.services.lifecycle import LifecycleService

    event = await group_event(db, group.id, event_id)
    # O endpoint público do ciclo continua sem avaliações. Aqui, a resposta
    # depende do solicitante: somente responsáveis recebem notas, inclusive a própria.
    if not await can_manage(db, group, profile):
        return {}
    players = await LifecycleService(db).event_players(event)
    profile_ids = {p.profile_id for p in players if p.profile_id}
    ratings = dict((await db.execute(select(GroupPlayerRating.profile_id, GroupPlayerRating.rating).where(
        GroupPlayerRating.group_id == group.id, GroupPlayerRating.profile_id.in_(profile_ids),
    ))).all())
    return {p.profile_id or p.guest_id: float(ratings[p.profile_id]) if p.profile_id in ratings else None
            for p in players}
