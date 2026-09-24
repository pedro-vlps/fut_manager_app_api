from uuid import UUID
from fastapi import APIRouter, Depends, Query
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.controllers import group_requests as controller
from src.models.entities import PeladaGroup, Profile
from src.routers.dependencies import accessible_group, current_profile
from src.schemas.group_requests import GroupCodeQuery, DiscoveredGroup, JoinRequestSchema, JoinRequestPerson, ReviewJoinRequest

router = APIRouter(tags=["Pedidos de entrada"])


@router.get("/group-discovery/search", response_model=DiscoveredGroup)
async def search(query: Annotated[GroupCodeQuery, Query()], profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.search(query, profile, db)


@router.post("/group-discovery/{group_id}/requests", response_model=JoinRequestSchema)
async def request_join(group_id: UUID, profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.request_join(group_id, profile, db)


@router.get("/my-groups/{group_id}/requests", response_model=list[JoinRequestPerson])
async def list_requests(group: PeladaGroup = Depends(accessible_group), profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.list_requests(group, profile, db)


@router.post("/my-groups/{group_id}/requests/{request_id}", response_model=JoinRequestSchema)
async def review(request_id: UUID, payload: ReviewJoinRequest, group: PeladaGroup = Depends(accessible_group), profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    return await controller.review(group, request_id, payload, profile, db)
