from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.controllers import draw as controller
from src.models.entities import PeladaGroup, Profile
from src.routers.dependencies import accessible_group, current_profile
from src.schemas.draw import DrawSettings, RatingUpdate, RatingView

router = APIRouter(prefix="/my-groups", tags=["Sorteio e avaliações privadas"])


@router.get("/{group_id}/events/{event_id}/team-ratings", response_model=dict[UUID, float | None])
async def team_ratings(event_id: UUID, group: PeladaGroup = Depends(accessible_group),
                       profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.team_ratings(db, group, profile, event_id)


@router.get("/{group_id}/draw-settings", response_model=DrawSettings)
async def settings(group: PeladaGroup = Depends(accessible_group), db: AsyncSession = Depends(get_db_session)):
    return await controller.get_settings(db, group)


@router.post("/{group_id}/draw-settings", response_model=DrawSettings)
async def update_settings(payload: DrawSettings, group: PeladaGroup = Depends(accessible_group),
                          profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.update_settings(db, group, profile, payload)


@router.get("/{group_id}/members/{profile_id}/rating", response_model=RatingView)
async def rating(profile_id: UUID, group: PeladaGroup = Depends(accessible_group),
                 profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.get_rating(db, group, profile, profile_id)


@router.post("/{group_id}/members/{profile_id}/rating", response_model=RatingView)
async def update_rating(profile_id: UUID, payload: RatingUpdate, group: PeladaGroup = Depends(accessible_group),
                        profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.update_rating(db, group, profile, profile_id, payload)
