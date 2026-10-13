from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime
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
    format: Literal["groups_knockout", "knockout", "cascade", "league"]
    capacity: int = Field(ge=2, strict=True)
    home_and_away: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def cascade_capacity(self):
        if self.format != "league" and self.capacity not in (4, 8, 12, 16):
            raise ValueError("Este formato permite 4, 8, 12 ou 16 times.")
        if self.capacity == 12 and self.format not in ("groups_knockout", "league"):
            raise ValueError("12 times está disponível somente para grupos + mata-mata.")
        if self.format == "cascade" and self.capacity != 4:
            raise ValueError("Cascata permite somente 4 times.")
        if self.home_and_away and self.format != "league":
            raise ValueError("Ida e volta está disponível somente para ligas.")
        return self


class Invite(Input):
    email: str = Field(min_length=3, max_length=255)


class Decision(Input):
    accept: bool


class Registration(Input):
    club_id: UUID


class GroupAssignment(Input):
    groups: list[list[UUID]] = Field(min_length=1, max_length=4)


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
    walkover: bool = False


class Punishment(Input):
    club_ids: list[UUID] = Field(min_length=1)
    kind: Literal['disqualification', 'points']
    points: int = Field(default=0, ge=0, strict=True)
    reason: str = Field(min_length=1, max_length=500)


class ClubTrophy(BaseModel):
    championship_id: UUID
    name: str
    season: str
    category: str


class MatchActionInput(Input):
    id: UUID
    team_id: UUID
    presence_id: UUID
    action_type: Literal['goal', 'assist', 'own_goal', 'yellow_card', 'red_card']


class MatchGoalkeepers(Input):
    home_goalkeeper_id: UUID | None = None
    away_goalkeeper_id: UUID | None = None


class StartingGoalkeeper(Input):
    goalkeeper_id: UUID | None


class GoalkeeperStint(BaseModel):
    team_id: UUID
    profile_id: UUID | None
    changed_at: datetime
    changed_by: UUID


class MatchActionView(MatchActionInput):
    player_name: str
    minute: int | None = None
    auto_generated: bool = False
    goalkeeper_id: UUID | None = None


class Person(BaseModel):
    id: UUID
    name: str
    status: str


class ClubView(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    members: list[Person]
    code: str | None = None
    trophies: list[ClubTrophy] = Field(default_factory=list)
    starting_goalkeeper_id: UUID | None = None


class InvitationView(BaseModel):
    id: UUID
    club_id: UUID
    club_name: str


class ChampionshipView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str | None = None
    name: str
    season: str
    description: str | None
    owner_id: UUID
    format: str
    capacity: int
    home_and_away: bool = False
    status: str
    champion_id: UUID | None


class EntryView(BaseModel):
    id: UUID
    club_id: UUID
    name: str
    seed: int
    pool: str | None = None
    players: list[Person]
    disqualified: bool = False
    points_deducted: int = 0
    punishments: list[dict] = Field(default_factory=list)
    owner_id: UUID | None = None
    starting_goalkeeper_id: UUID | None = None


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
    home_goalkeeper_id: UUID | None = None
    away_goalkeeper_id: UUID | None = None
    statistics_complete: bool
    actions: list[MatchActionView] = Field(default_factory=list)
    walkover: bool = False
    bracket_size: int | None = None
    started_at: datetime | None = None
    goalkeeper_history: list[GoalkeeperStint] = Field(default_factory=list)
    home_goalkeeper_override: bool = False
    away_goalkeeper_override: bool = False


class PlayerRanking(BaseModel):
    profile_id: UUID
    name: str
    club_id: UUID
    goals: int = 0
    assists: int = 0
    own_goals: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    losses: int = 0
    goals_conceded: int = 0
    matches: int = 0
    goalkeeper_matches: int = 0
    team_position: int = 0


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
    wins: int = 0
    draws: int = 0
    losses: int = 0
    disqualified: bool = False


class ChampionshipDetail(ChampionshipView):
    entries: list[EntryView]
    matches: list[MatchView]
    standings: list[Standing]
    general_standings: list[Standing]
    player_rankings: list[PlayerRanking]
    statistics_complete: bool
    trophies: list[ChampionshipAward]


class CreatedGroup(BaseModel):
    id: UUID


class ChampionshipCodeQuery(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9]{6}$")
