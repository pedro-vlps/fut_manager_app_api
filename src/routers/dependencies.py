from uuid import UUID
from fastapi import Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.models.entities import Profile, PeladaGroup
from src.controllers import auth, groups, lifecycle

bearer = HTTPBearer(auto_error=False)


async def current_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db_session),
) -> Profile:
    return await auth.current_profile(credentials, db)


async def accessible_group(
    group_id: UUID,
    response: Response,
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await groups.accessible_group(group_id, response, profile, db)


async def managed_event(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await lifecycle.managed_event(event_id, group, profile, db)
