"""Enumerações persistidas pelo domínio de peladas."""

from enum import StrEnum


class GroupRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    BLOCKED = "blocked"


class EventStatus(StrEnum):
    DRAFT = "draft"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class PresenceStatus(StrEnum):
    REGISTERED = "registered"
    CONFIRMED = "confirmed"
    WAITLIST = "waitlist"
    CANCELLED = "cancelled"
    ABSENT = "absent"


class TeamPlayerRole(StrEnum):
    PLAYER = "player"
    GOALKEEPER = "goalkeeper"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class MatchResult(StrEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


class GameActionType(StrEnum):
    GOAL = "goal"
    OWN_GOAL = "own_goal"
    ASSIST = "assist"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
