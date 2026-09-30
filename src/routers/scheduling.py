from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import PeladaGroup, Profile
from src.configs.db_connection import get_db_session
from src.routers.dependencies import accessible_group, current_profile
from src.schemas.scheduling import ScheduleRequest
from src.schemas.events import PeladaEventSchema
from src.controllers import scheduling as controller

router = APIRouter(prefix="/my-groups", tags=["Agendamento"])


@router.post("/{group_id}/schedule", response_model=PeladaEventSchema)
async def schedule(payload: ScheduleRequest, group: PeladaGroup = Depends(accessible_group),
                   profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.schedule(payload, group, profile, db)
