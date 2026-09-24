from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configs.db_connection import get_db_session
from src.models.entities import PeladaEvent, PeladaGroup, Profile
from src.schemas.lifecycle import (
    ActionRequest,
    FinishRequest,
    KickoffRequest,
    LifecycleView,
    TeamsRequest,
    TimerRequest,
)
from src.controllers import lifecycle as controller
from src.routers.dependencies import current_profile, accessible_group, managed_event

router = APIRouter(
    prefix="/my-groups/{group_id}/events/{event_id}", tags=["Ciclo do evento"]
)


@router.get("/lifecycle", response_model=LifecycleView)
async def get_lifecycle(
    event_id: UUID,
    group: PeladaGroup = Depends(accessible_group),
    profile: Profile = Depends(current_profile),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.get_lifecycle(event_id, group, profile, db)


@router.post("/teams", response_model=LifecycleView)
async def build_teams(
    payload: TeamsRequest,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.build_teams(payload, event, db)


@router.post("/start", response_model=LifecycleView)
async def start(
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.start(event, db)


@router.post("/kickoff", response_model=LifecycleView)
async def kickoff(
    payload: KickoffRequest,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.kickoff(payload, event, db)


@router.post("/matches/{match_id}/timer", response_model=LifecycleView)
async def control_timer(
    match_id: UUID,
    payload: TimerRequest,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.control_timer(match_id, payload, event, db)


@router.post("/matches/{match_id}/actions", response_model=LifecycleView)
async def add_action(
    match_id: UUID,
    payload: ActionRequest,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.add_action(match_id, payload, event, db)


@router.post(
    "/matches/{match_id}/actions/{action_id}/remove", response_model=LifecycleView
)
async def remove_action(
    match_id: UUID,
    action_id: UUID,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.remove_action(match_id, action_id, event, db)


@router.post("/matches/{match_id}/finish", response_model=LifecycleView)
async def finish_match(
    match_id: UUID,
    payload: FinishRequest,
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.finish_match(match_id, payload, event, db)


@router.post("/finish", response_model=LifecycleView)
async def finish_event(
    event: PeladaEvent = Depends(managed_event),
    db: AsyncSession = Depends(get_db_session),
):
    return await controller.finish_event(event, db)
