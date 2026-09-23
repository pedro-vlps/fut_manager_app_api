"""Login e consultas da conta autenticada.

Sessões opacas ficam na memória deste processo e expiram em oito horas.
"""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.configs.db_connection import get_db_session
from src.helpers.passwords import hash_password, verify_password
from src.models.entities import GroupMember, PeladaGroup, Profile
from src.models.enums import GroupRole, MembershipStatus
from src.schemas.crud import PeladaGroupSchema, ProfileSchema, ProfileCreateSchema
from src.schemas.player_positions import MODALITIES, PlayerPositions

router = APIRouter(prefix="/auth", tags=["Autenticação"])
bearer = HTTPBearer(auto_error=False)
_sessions: dict[str, tuple[UUID, datetime]] = {}
_session_lock = Lock()
_dummy_hash = hash_password(token_urlsafe(32))


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: ProfileSchema


class MyGroupResponse(PeladaGroupSchema):
    role: GroupRole

@router.get('/modalities')
async def modalities():
    return MODALITIES

@router.post('/register', response_model=ProfileSchema, status_code=201)
async def register(payload: ProfileCreateSchema, db: AsyncSession = Depends(get_db_session)):
    import re
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if not name or len(name) > 120 or len(email) > 255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Informe um nome e e-mail válidos.')
    if await db.scalar(select(Profile.id).where(func.lower(Profile.email) == email)):
        raise HTTPException(409, 'Já existe uma conta com este e-mail.')
    profile = Profile(name=name, email=email, positions=payload.positions, is_active=True)
    profile.password_hash = await run_in_threadpool(hash_password, payload.password)
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Já existe uma conta com este e-mail.')
    await db.refresh(profile)
    return profile


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Sessão inválida ou expirada. Entre novamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db_session),
) -> Profile:
    if credentials is None:
        raise unauthorized()
    with _session_lock:
        session = _sessions.get(credentials.credentials)
        if session is None or session[1] <= datetime.now(timezone.utc):
            _sessions.pop(credentials.credentials, None)
            raise unauthorized()
    profile = await db.get(Profile, session[0])
    if profile is None or not profile.is_active:
        raise unauthorized()
    return profile


class MyPositionsRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    positions: PlayerPositions

@router.get('/me', response_model=ProfileSchema)
async def my_profile(response: Response, profile: Profile = Depends(current_profile)):
    response.headers['Cache-Control'] = 'no-store'
    return profile

@router.post('/me/positions', response_model=ProfileSchema)
async def update_my_positions(payload: MyPositionsRequest, response: Response,
    profile: Profile = Depends(current_profile), db: AsyncSession = Depends(get_db_session)):
    profile.positions = payload.positions
    await db.commit()
    await db.refresh(profile)
    response.headers['Cache-Control'] = 'no-store'
    return profile

@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    # Ambiguous legacy emails differing only in case cannot select another account.
    profiles = (await db.scalars(select(Profile).where(
        func.lower(Profile.email) == payload.email.strip().lower()
    ))).all()
    profile = profiles[0] if len(profiles) == 1 else None
    valid = await run_in_threadpool(
        verify_password, payload.password,
        profile.password_hash if profile else _dummy_hash,
    )
    if not valid or profile is None or not profile.is_active:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    now = datetime.now(timezone.utc)
    token = token_urlsafe(32)
    with _session_lock:
        for expired in [key for key, (_, expiry) in _sessions.items() if expiry <= now]:
            del _sessions[expired]
        _sessions[token] = (profile.id, now + timedelta(hours=8))
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(access_token=token, profile=ProfileSchema.model_validate(profile))


@router.get("/me/groups", response_model=list[MyGroupResponse])
async def my_groups(
    response: Response,
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    membership = select(GroupMember.group_id).where(
        GroupMember.profile_id == profile.id,
        GroupMember.status == MembershipStatus.ACTIVE,
    )
    rows = (await db.execute(
        select(PeladaGroup, GroupMember.role)
        .outerjoin(GroupMember, (GroupMember.group_id == PeladaGroup.id)
                   & (GroupMember.profile_id == profile.id))
        .where(or_(PeladaGroup.created_by_id == profile.id, PeladaGroup.id.in_(membership)))
        .order_by(func.lower(PeladaGroup.name), PeladaGroup.id)
    )).all()
    response.headers["Cache-Control"] = "no-store"
    return [MyGroupResponse(
        **PeladaGroupSchema.model_validate(group).model_dump(),
        role=GroupRole.OWNER if group.created_by_id == profile.id else role,
    ) for group, role in rows]


@router.post("/logout", status_code=204)
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials:
        with _session_lock:
            _sessions.pop(credentials.credentials, None)
    return Response(status_code=204)
