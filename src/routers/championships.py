from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.models.entities import Profile
from src.routers.dependencies import current_profile
from src.controllers import championships as controller
from src.schemas.member_profile import MemberProfile
from src.schemas.championships import (NamedInput, ChampionshipCreate, Invite, Decision, Registration, Score,
    ClubView, InvitationView, ChampionshipView, ChampionshipDetail, CreatedGroup, ChampionshipCodeQuery, MatchActionInput)

router = APIRouter(tags=["Campeonatos e times"])
User = Annotated[Profile, Depends(current_profile)]
DB = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/championship-discovery/search", response_model=ChampionshipView)
async def search_by_code(query: Annotated[ChampionshipCodeQuery, Query()], profile: User, db: DB):
    return await controller.search_by_code(query, profile, db)


@router.post("/my-groups", response_model=CreatedGroup, status_code=201)
async def create_group(payload: NamedInput, profile: User, db: DB):
    return await controller.create_group(payload, profile, db)


@router.get("/clubs", response_model=list[ClubView])
async def clubs(profile: User, db: DB):
    return await controller.my_clubs(profile, db)


@router.post("/clubs", response_model=ClubView, status_code=201)
async def create_club(payload: NamedInput, profile: User, db: DB):
    return await controller.create_club(payload, profile, db)


@router.post("/clubs/{club_id}/invitations", response_model=ClubView)
async def invite(club_id: UUID, payload: Invite, profile: User, db: DB):
    return await controller.invite(club_id, payload, profile, db)


@router.get("/club-invitations", response_model=list[InvitationView])
async def invitations(profile: User, db: DB):
    return await controller.invitations(profile, db)


@router.post("/club-invitations/{invitation_id}", status_code=204)
async def respond(invitation_id: UUID, payload: Decision, profile: User, db: DB):
    return await controller.respond(invitation_id, payload, profile, db)


@router.get("/championships", response_model=list[ChampionshipView])
async def championships(profile: User, db: DB):
    return await controller.list_championships(profile, db)


@router.post("/championships", response_model=ChampionshipView, status_code=201)
async def create_championship(payload: ChampionshipCreate, profile: User, db: DB):
    return await controller.create_championship(payload, profile, db)


@router.get("/championships/{championship_id}", response_model=ChampionshipDetail)
async def detail(championship_id: UUID, profile: User, db: DB):
    return await controller.detail(championship_id, profile, db)


@router.post("/championships/{championship_id}/entries", response_model=ChampionshipDetail)
async def register(championship_id: UUID, payload: Registration, profile: User, db: DB):
    return await controller.register(championship_id, payload, profile, db)


@router.get("/championships/{championship_id}/clubs/{club_id}/players/{profile_id}", response_model=MemberProfile)
async def player_profile(championship_id: UUID, club_id: UUID, profile_id: UUID, profile: User, db: DB):
    return await controller.player_profile(championship_id, club_id, profile_id, profile, db)


@router.post("/championships/{championship_id}/entries/{club_id}/withdraw", response_model=ChampionshipDetail)
async def withdraw(championship_id: UUID, club_id: UUID, profile: User, db: DB):
    return await controller.withdraw(championship_id, club_id, profile, db)


@router.post("/championships/{championship_id}/start", response_model=ChampionshipDetail)
async def start(championship_id: UUID, profile: User, db: DB):
    return await controller.start(championship_id, profile, db)


@router.post("/championships/{championship_id}/matches/{match_id}/score", response_model=ChampionshipDetail)
async def score(championship_id: UUID, match_id: UUID, payload: Score, profile: User, db: DB):
    return await controller.score(championship_id, match_id, payload, profile, db)


@router.post("/championships/{championship_id}/matches/{match_id}/actions", response_model=ChampionshipDetail)
async def add_action(championship_id: UUID, match_id: UUID, payload: MatchActionInput, profile: User, db: DB):
    return await controller.add_action(championship_id, match_id, payload, profile, db)


@router.post("/championships/{championship_id}/matches/{match_id}/actions/{action_id}/remove", response_model=ChampionshipDetail)
async def remove_action(championship_id: UUID, match_id: UUID, action_id: UUID, profile: User, db: DB):
    return await controller.remove_action(championship_id, match_id, action_id, profile, db)
