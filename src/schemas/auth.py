from pydantic import BaseModel, Field
from src.models.enums import GroupRole
from src.schemas.player_positions import PlayerPositions
from src.schemas.profiles import ProfileSchema
from src.schemas.groups import PeladaGroupSchema


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: ProfileSchema


class MyGroupResponse(PeladaGroupSchema):
    role: GroupRole


class MyPositionsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    positions: PlayerPositions


class ModalitySchema(BaseModel):
    label: str
    positions: dict[str, str]
