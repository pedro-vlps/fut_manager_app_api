"""Contratos do ciclo de evento e da súmula de cada partida."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from src.models.enums import GameActionType, TeamPlayerRole
from src.schemas.crud import PeladaEventSchema

class PlayerSelection(BaseModel):
    presence_id: UUID
    role: TeamPlayerRole = TeamPlayerRole.PLAYER

class TeamSelection(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    players: list[PlayerSelection] = Field(min_length=1)

class TeamsRequest(BaseModel):
    mode: Literal['random', 'manual']
    team_count: int = Field(default=3, ge=3, le=4)
    teams: list[TeamSelection] = Field(default_factory=list, max_length=4)

class KickoffRequest(BaseModel):
    mode: Literal['random', 'manual']
    team_ids: list[UUID] = Field(default_factory=list, max_length=2)

class ActionRequest(BaseModel):
    id: UUID
    team_id: UUID
    presence_id: UUID
    action_type: GameActionType
    minute: int | None = Field(default=None, ge=0, le=999)

class FinishRequest(BaseModel):
    advancing_team_id: UUID | None = None
    random_tiebreak: bool = False
    continue_cycle: bool = True

class TimerRequest(BaseModel):
    action: Literal['play', 'pause']

class Participant(BaseModel):
    presence_id: UUID
    person_id: UUID
    name: str
    is_guest: bool
    role: TeamPlayerRole = TeamPlayerRole.PLAYER

class TeamView(BaseModel):
    id: UUID
    name: str
    color: str | None
    players: list[Participant]

class ScoreView(BaseModel):
    team_id: UUID
    name: str
    goals: int
    result: str | None

class ActionView(BaseModel):
    id: UUID
    team_id: UUID
    player_name: str
    action_type: GameActionType
    minute: int | None

class MatchView(BaseModel):
    id: UUID
    sequence: int
    status: str
    advancing_team_id: UUID | None
    scores: list[ScoreView]
    actions: list[ActionView]
    timer_elapsed_ms: int
    timer_running: bool

class LifecycleView(BaseModel):
    event: PeladaEventSchema
    can_manage: bool
    participants: list[Participant]
    teams: list[TeamView]
    waiting_team_ids: list[UUID]
    current_match: MatchView | None
    matches: list[MatchView]
