from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.models.entities import Profile
from src.schemas.profiles import ProfileSchema
from src.schemas.profiles import ProfileCreateSchema
from src.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MyGroupResponse,
    MyPositionsRequest,
    ModalitySchema,
)
from src.controllers import auth as controller
from src.routers.dependencies import current_profile, bearer
from src.controllers.auth import _sessions

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.get("/modalities", response_model=dict[str, ModalitySchema])
async def modalities():
    return await controller.modalities()


@router.post("/register", response_model=ProfileSchema, status_code=201)
async def register(
    payload: ProfileCreateSchema, db: AsyncSession = Depends(get_db_session)
):
    return await controller.register(payload, db)


@router.get("/me", response_model=ProfileSchema)
async def my_profile(response: Response, profile: Profile = Depends(current_profile)):
    return await controller.my_profile(response, profile)


@router.post("/me/positions", response_model=ProfileSchema)
async def update_my_positions(
    payload: MyPositionsRequest,
    response: Response,
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.update_my_positions(payload, response, profile, db)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.login(payload, response, db)


@router.get("/me/groups", response_model=list[MyGroupResponse])
async def my_groups(
    response: Response,
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.my_groups(response, profile, db)


@router.post("/logout", status_code=204)
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    return await controller.logout(credentials)
