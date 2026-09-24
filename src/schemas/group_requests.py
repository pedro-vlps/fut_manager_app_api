from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class GroupCodeQuery(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9]{6}$")


class DiscoveredGroup(BaseModel):
    id: UUID
    name: str
    code: str
    description: str | None
    membership: Literal["active", "blocked", "none"]
    request_status: Literal["pending", "approved", "rejected"] | None


class JoinRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    group_id: UUID
    profile_id: UUID
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    reviewed_at: datetime | None


class JoinRequestPerson(JoinRequestSchema):
    name: str


class ReviewJoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
