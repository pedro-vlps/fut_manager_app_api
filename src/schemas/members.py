from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel as SCBaseModel
from src.models.enums import GroupRole, MembershipStatus


class GroupMemberSchema(SCBaseModel):
    id: Optional[UUID] = None
    group_id: UUID
    profile_id: UUID
    role: GroupRole
    status: MembershipStatus
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "member",
                "status": "active",
            }
        }


class GroupMemberCreateSchema(SCBaseModel):
    group_id: UUID
    profile_id: UUID
    role: GroupRole = GroupRole.MEMBER
    status: MembershipStatus = MembershipStatus.ACTIVE

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "group_id": "550e8400-e29b-41d4-a716-446655440001",
                "profile_id": "550e8400-e29b-41d4-a716-446655440002",
                "role": "member",
                "status": "active",
            }
        }


class GroupMemberUpdateSchema(SCBaseModel):
    role: Optional[GroupRole] = None
    status: Optional[MembershipStatus] = None

    class Config:
        from_attributes = True
        json_schema_extra = {"example": {"role": "admin"}}
