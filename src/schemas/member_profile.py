from uuid import UUID
from pydantic import BaseModel
from src.schemas.trophies import TrophyCollection


class MemberProfile(BaseModel):
    id: UUID
    name: str
    positions: dict[str, list[str]]
    trophies: TrophyCollection
    can_rate: bool = False
