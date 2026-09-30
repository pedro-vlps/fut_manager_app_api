from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.controllers import trophies as controller
from src.models.entities import Profile
from src.routers.dependencies import current_profile
from src.schemas.trophies import TrophyCollection

router = APIRouter(prefix="/auth/me", tags=["Troféus"])


@router.get("/trophies", response_model=TrophyCollection)
async def my_trophies(profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.my_trophies(profile, db)
