from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from src.schemas.trophies import TrophySchema

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NamedInput(Input):
    name: Name


class ChampionshipCreate(NamedInput):
    season: Name
    description: str | None = Field(default=None, max_length=2000)
    format: Literal["groups_knockout", "knockout", "cascade"]
    capacity: Literal[4, 8, 16]

    @model_validator(mode="after")
    def cascade_capacity(self):
        if self.format == "cascade" and self.capacity != 4:
            raise ValueError("Cascata permite somente 4 times.")
        return self


class Invite(Input):
    email: str = Field(min_length=3, max_length=255)


class Decision(Input):
    accept: bool


class Registration(Input):
    club_id: UUID


class PlayerStatistic(Input):
    profile_id: UUID
    goals: int = Field(default=0, ge=0, le=999, strict=True)
    assists: int = Field(default=0, ge=0, le=999, strict=True)
    own_goals: int = Field(default=0, ge=0, le=999, strict=True)


class Score(Input):
    home_score: int = Field(ge=0, le=999, strict=True)
    away_score: int = Field(ge=0, le=999, strict=True)
    winner_id: UUID | None = None
    statistics: list[PlayerStatistic] | None = Field(default=None, max_length=200)
    action_ids: list[UUID] | None = Field(default=None, max_length=5000)


class MatchActionInput(Input):
    id: UUID
    team_id: UUID
    presence_id: UUID
    action_type: Literal['goal', 'assist', 'own_goal', 'yellow_card', 'red_card']


class MatchActionView(MatchActionInput):
    player_name: str
    minute: int | None = None


class Person(BaseModel):
    id: UUID
    name: str
    status: str


class ClubView(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    members: list[Person]


class InvitationView(BaseModel):
    id: UUID
    club_id: UUID
    club_name: str


class ChampionshipView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    season: str
    description: str | None
    owner_id: UUID
    format: str
    capacity: int
    status: str
    champion_id: UUID | None


class EntryView(BaseModel):
    id: UUID
    club_id: UUID
    name: str
    seed: int
    players: list[Person]


class MatchView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    stage: str
    round: int
    pool: str | None
    home_id: UUID
    away_id: UUID
    home_score: int | None
    away_score: int | None
    winner_id: UUID | None
    statistics_complete: bool
    actions: list[MatchActionView] = Field(default_factory=list)


class PlayerRanking(BaseModel):
    profile_id: UUID
    name: str
    club_id: UUID
    goals: int = 0
    assists: int = 0
    own_goals: int = 0


class ChampionshipAward(TrophySchema):
    profile_id: UUID
    name: str


class Standing(BaseModel):
    club_id: UUID
    pool: str
    played: int
    points: int
    goals_for: int
    goals_against: int
    seed: int


class ChampionshipDetail(ChampionshipView):
    entries: list[EntryView]
    matches: list[MatchView]
    standings: list[Standing]
    player_rankings: list[PlayerRanking]
    statistics_complete: bool
    trophies: list[ChampionshipAward]


class CreatedGroup(BaseModel):
    id: UUID


class ChampionshipCodeQuery(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9]{6}$")
