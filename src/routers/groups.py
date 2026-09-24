from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.models.entities import PeladaGroup, Profile
from src.schemas.presences import EventPresenceSchema
from src.schemas.events import PeladaEventSchema
from src.schemas.groups import GroupOverview, Person, RankingEntry
from src.controllers import groups as controller
from src.routers.dependencies import current_profile, accessible_group

router = APIRouter(prefix="/my-groups", tags=["Área do grupo"])


@router.get("/{group_id}", response_model=GroupOverview)
async def overview(
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.overview(group, profile, db)


@router.post(
    "/{group_id}/events/{event_id}/confirm", response_model=EventPresenceSchema
)
async def confirm(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.confirm(event_id, group, profile, db)


@router.get("/{group_id}/events/{event_id}/confirmed", response_model=list[Person])
async def confirmed(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.confirmed(event_id, group, db)


@router.get("/{group_id}/history", response_model=list[PeladaEventSchema])
async def history(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.history(group, db)


@router.get("/{group_id}/members", response_model=list[Person])
async def members(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.members(group, db)


@router.get("/{group_id}/rankings", response_model=list[RankingEntry])
async def rankings(
    group: PeladaGroup = Depends(accessible_group),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.rankings(group, db)
