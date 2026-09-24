from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import Lock
from uuid import UUID
from fastapi import HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from src.helpers.passwords import hash_password, verify_password
from src.models.entities import Profile
from src.models.enums import GroupRole
from src.schemas.groups import PeladaGroupSchema
from src.schemas.profiles import ProfileSchema
from src.schemas.profiles import ProfileCreateSchema
from src.schemas.player_positions import MODALITIES
from src.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MyGroupResponse,
    MyPositionsRequest,
)
from src.services.auth import AuthService
from src.helpers.auth import unauthorized

_sessions: dict[str, tuple[UUID, datetime]] = {}
_session_lock = Lock()
_dummy_hash = hash_password(token_urlsafe(32))


async def modalities():
    return MODALITIES


async def register(payload: ProfileCreateSchema, db: AsyncSession):
    service = AuthService(db)
    import re

    email = payload.email.strip().lower()
    name = payload.name.strip()
    if (
        not name
        or len(name) > 120
        or len(email) > 255
        or (not re.fullmatch("[^\\s@]+@[^\\s@]+\\.[^\\s@]+", email))
    ):
        raise HTTPException(422, "Informe um nome e e-mail válidos.")
    if await service.find_profile_id_by_email(email):
        raise HTTPException(409, "Já existe uma conta com este e-mail.")
    profile = Profile(
        name=name, email=email, positions=payload.positions, is_active=True
    )
    profile.password_hash = await run_in_threadpool(hash_password, payload.password)
    service.add(profile)
    try:
        await service.commit()
    except IntegrityError:
        await service.rollback()
        raise HTTPException(409, "Já existe uma conta com este e-mail.")
    await service.refresh(profile)
    return profile


async def current_profile(
    credentials: HTTPAuthorizationCredentials | None, db: AsyncSession
) -> Profile:
    service = AuthService(db)
    if credentials is None:
        raise unauthorized()
    with _session_lock:
        session = _sessions.get(credentials.credentials)
        if session is None or session[1] <= datetime.now(timezone.utc):
            _sessions.pop(credentials.credentials, None)
            raise unauthorized()
    profile = await service.get(Profile, session[0])
    if profile is None or not profile.is_active:
        raise unauthorized()
    return profile


async def my_profile(response: Response, profile: Profile):
    response.headers["Cache-Control"] = "no-store"
    return profile


async def update_my_positions(
    payload: MyPositionsRequest, response: Response, profile: Profile, db: AsyncSession
):
    service = AuthService(db)
    profile.positions = payload.positions
    await service.commit()
    await service.refresh(profile)
    response.headers["Cache-Control"] = "no-store"
    return profile


async def login(payload: LoginRequest, response: Response, db: AsyncSession):
    service = AuthService(db)
    profiles = await service.profiles_by_email(payload.email.strip().lower())
    profile = profiles[0] if len(profiles) == 1 else None
    valid = await run_in_threadpool(
        verify_password,
        payload.password,
        profile.password_hash if profile else _dummy_hash,
    )
    if not valid or profile is None or (not profile.is_active):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    now = datetime.now(timezone.utc)
    token = token_urlsafe(32)
    with _session_lock:
        for expired in [key for key, (_, expiry) in _sessions.items() if expiry <= now]:
            del _sessions[expired]
        _sessions[token] = (profile.id, now + timedelta(hours=8))
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        access_token=token, profile=ProfileSchema.model_validate(profile)
    )


async def my_groups(response: Response, profile: Profile, db: AsyncSession):
    service = AuthService(db)
    rows = await service.groups_for_profile(profile)
    response.headers["Cache-Control"] = "no-store"
    return [
        MyGroupResponse(
            **PeladaGroupSchema.model_validate(group).model_dump(),
            role=GroupRole.OWNER if group.created_by_id == profile.id else role,
        )
        for group, role in rows
    ]


async def logout(credentials: HTTPAuthorizationCredentials | None):
    if credentials:
        with _session_lock:
            _sessions.pop(credentials.credentials, None)
    return Response(status_code=204)
