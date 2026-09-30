from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.controllers import seasons as controller
from src.models.entities import PeladaGroup, Profile
from src.routers.dependencies import accessible_group, current_profile
from src.schemas.seasons import SeasonSettings, SeasonSettingsUpdate, SeasonHistory, SeasonRankings

router = APIRouter(prefix="/my-groups", tags=["Temporadas"])


@router.get("/{group_id}/settings", response_model=SeasonSettings)
async def settings(group: PeladaGroup = Depends(accessible_group), profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.settings(group, profile, db)


@router.post("/{group_id}/settings", response_model=SeasonSettings)
async def update_settings(payload: SeasonSettingsUpdate, group: PeladaGroup = Depends(accessible_group), profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.update_settings(group, payload, profile, db)


@router.get("/{group_id}/seasons", response_model=SeasonHistory)
async def history(group: PeladaGroup = Depends(accessible_group), db: AsyncSession = Depends(get_db_session)):
    return await controller.history(group, db)


@router.get("/{group_id}/season-rankings", response_model=SeasonRankings)
async def current_rankings(group: PeladaGroup = Depends(accessible_group), db: AsyncSession = Depends(get_db_session)):
    return await controller.current_rankings(group, db)


@router.get("/{group_id}/seasons/{season_id}/rankings", response_model=SeasonRankings)
async def historical_rankings(season_id: UUID, group: PeladaGroup = Depends(accessible_group), db: AsyncSession = Depends(get_db_session)):
    return await controller.historical_rankings(group, season_id, db)
