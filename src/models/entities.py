"""Modelo relacional do domínio: grupos, eventos, times, jogos e estatísticas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    FetchedValue,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.helpers.passwords import hash_password, verify_password
from src.models.base import Base, UUIDTimestampMixin
from src.models.enums import (
    EventStatus,
    GameActionType,
    GroupRole,
    MatchResult,
    MatchStatus,
    MembershipStatus,
    PresenceStatus,
    TeamPlayerRole,
)


class Profile(UUIDTimestampMixin, Base):
    __tablename__ = "profiles"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    positions: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    group_memberships: Mapped[list[GroupMember]] = relationship(
        back_populates="profile"
    )
    created_guests: Mapped[list[GroupGuest]] = relationship(back_populates="created_by")
    event_presences: Mapped[list[EventPresence]] = relationship(
        back_populates="profile"
    )
    team_assignments: Mapped[list[EventTeamPlayer]] = relationship(
        back_populates="profile"
    )
    lineup_entries: Mapped[list[MatchLineup]] = relationship(back_populates="profile")
    game_actions: Mapped[list[GameAction]] = relationship(back_populates="player")

    @property
    def password(self) -> None:
        """Nunca expõe a senha ou seu hash pela entidade."""
        return None

    @password.setter
    def password(self, value: str) -> None:
        self.password_hash = hash_password(value)

    def verify_password(self, password: str) -> bool:
        """Verifica uma tentativa de login contra o hash armazenado."""
        return verify_password(password, self.password_hash)


class PeladaGroup(UUIDTimestampMixin, Base):
    __tablename__ = "pelada_groups"
    __table_args__ = (UniqueConstraint('code', name='pelada_groups_code_unique'),)

    code: Mapped[str] = mapped_column(String(6), server_default=FetchedValue(), nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False
    )

    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    guests: Mapped[list[GroupGuest]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    events: Mapped[list[PeladaEvent]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMember(UUIDTimestampMixin, Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "profile_id"),)

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_groups.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    role: Mapped[GroupRole] = mapped_column(
        Enum(GroupRole, name="group_role"), default=GroupRole.MEMBER, nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus, name="membership_status"),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )

    group: Mapped[PeladaGroup] = relationship(back_populates="members")
    profile: Mapped[Profile] = relationship(back_populates="group_memberships")


class GroupJoinRequest(UUIDTimestampMixin, Base):
    __tablename__ = "group_join_requests"
    __table_args__ = (
        UniqueConstraint("group_id", "profile_id"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="join_request_status"),
    )

    group_id: Mapped[UUID] = mapped_column(ForeignKey("pelada_groups.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", nullable=False)
    reviewed_by_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("profiles.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class GroupGuest(UUIDTimestampMixin, Base):
    """Jogador convidado, sem conta, incluído por um membro ativo da pelada."""

    __tablename__ = "group_guests"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_groups.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    group: Mapped[PeladaGroup] = relationship(back_populates="guests")
    created_by: Mapped[Profile] = relationship(back_populates="created_guests")
    event_presences: Mapped[list[EventPresence]] = relationship(back_populates="guest")
    team_assignments: Mapped[list[EventTeamPlayer]] = relationship(
        back_populates="guest"
    )
    lineup_entries: Mapped[list[MatchLineup]] = relationship(back_populates="guest")
    game_actions: Mapped[list[GameAction]] = relationship(back_populates="guest")


class PeladaEvent(UUIDTimestampMixin, Base):
    __tablename__ = "pelada_events"
    __table_args__ = (
        CheckConstraint(
            "max_confirmed_players IS NULL OR max_confirmed_players > 0",
            name="positive_max_confirmed_players",
        ),
        CheckConstraint(
            "min_confirmed_players IS NULL OR min_confirmed_players > 0",
            name="positive_min_confirmed_players",
        ),
        CheckConstraint(
            "min_confirmed_players IS NULL OR max_confirmed_players IS NULL "
            "OR min_confirmed_players <= max_confirmed_players",
            name="min_confirmed_not_greater_than_max",
        ),
        CheckConstraint(
            "match_duration_minutes IS NULL OR match_duration_minutes > 0",
            name="positive_match_duration",
        ),
        Index("ix_pelada_events_group_scheduled_at", "group_id", "scheduled_at"),
    )

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_groups.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    registration_opens_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    registration_closes_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    min_confirmed_players: Mapped[Optional[int]] = mapped_column(Integer)
    max_confirmed_players: Mapped[Optional[int]] = mapped_column(Integer)
    match_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"),
        default=EventStatus.DRAFT,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    group: Mapped[PeladaGroup] = relationship(back_populates="events")
    presences: Mapped[list[EventPresence]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    teams: Mapped[list[EventTeam]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    queue_entries: Mapped[list[EventTeamQueueEntry]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    matches: Mapped[list[Match]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventPresence(UUIDTimestampMixin, Base):
    __tablename__ = "event_presences"
    __table_args__ = (
        UniqueConstraint("event_id", "profile_id", name="uq_event_presence_profile"),
        UniqueConstraint("event_id", "guest_id", name="uq_event_presence_guest"),
        Index("ix_event_presences_event_status", "event_id", "status"),
        Index(
            "uq_event_presences_waitlist_position",
            "event_id",
            "waitlist_position",
            unique=True,
            postgresql_where=text(
                "status = 'WAITLIST' AND waitlist_position IS NOT NULL"
            ),
        ),
        CheckConstraint(
            "waitlist_position IS NULL OR waitlist_position > 0",
            name="positive_waitlist_position",
        ),
        CheckConstraint(
            "(profile_id IS NOT NULL AND guest_id IS NULL) OR "
            "(profile_id IS NULL AND guest_id IS NOT NULL)",
            name="profile_or_guest_presence",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_events.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("profiles.id"))
    guest_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("group_guests.id", ondelete="CASCADE")
    )
    status: Mapped[PresenceStatus] = mapped_column(
        Enum(PresenceStatus, name="presence_status"),
        default=PresenceStatus.REGISTERED,
        nullable=False,
    )
    waitlist_position: Mapped[Optional[int]] = mapped_column(Integer)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    event: Mapped[PeladaEvent] = relationship(back_populates="presences")
    profile: Mapped[Profile] = relationship(back_populates="event_presences")
    guest: Mapped[Optional[GroupGuest]] = relationship(back_populates="event_presences")


class EventTeam(UUIDTimestampMixin, Base):
    __tablename__ = "event_teams"
    __table_args__ = (UniqueConstraint("event_id", "name"),)

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_events.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7))
    draw_order: Mapped[Optional[int]] = mapped_column(Integer)

    event: Mapped[PeladaEvent] = relationship(back_populates="teams")
    players: Mapped[list[EventTeamPlayer]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    queue_entry: Mapped[Optional[EventTeamQueueEntry]] = relationship(
        back_populates="team", uselist=False, cascade="all, delete-orphan"
    )
    match_entries: Mapped[list[MatchTeam]] = relationship(back_populates="team")


class EventTeamPlayer(UUIDTimestampMixin, Base):
    __tablename__ = "event_team_players"
    __table_args__ = (
        UniqueConstraint("team_id", "profile_id", name="uq_event_team_player_profile"),
        UniqueConstraint("team_id", "guest_id", name="uq_event_team_player_guest"),
        CheckConstraint(
            "(profile_id IS NOT NULL AND guest_id IS NULL) OR "
            "(profile_id IS NULL AND guest_id IS NOT NULL)",
            name="profile_or_guest_team_player",
        ),
    )

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_teams.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("profiles.id"))
    guest_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("group_guests.id", ondelete="CASCADE")
    )
    role: Mapped[TeamPlayerRole] = mapped_column(
        Enum(TeamPlayerRole, name="team_player_role"),
        default=TeamPlayerRole.PLAYER,
        nullable=False,
    )

    team: Mapped[EventTeam] = relationship(back_populates="players")
    profile: Mapped[Profile] = relationship(back_populates="team_assignments")
    guest: Mapped[Optional[GroupGuest]] = relationship(
        back_populates="team_assignments"
    )


class EventTeamQueueEntry(UUIDTimestampMixin, Base):
    """Posição atual de um time na fila de confrontos de um evento em andamento."""

    __tablename__ = "event_team_queue_entries"
    __table_args__ = (
        UniqueConstraint("event_id", "team_id", name="uq_event_team_queue_event_team"),
        UniqueConstraint(
            "event_id", "position", name="uq_event_team_queue_event_position"
        ),
        CheckConstraint("position > 0", name="positive_queue_position"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_events.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_teams.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    event: Mapped[PeladaEvent] = relationship(back_populates="queue_entries")
    team: Mapped[EventTeam] = relationship(back_populates="queue_entry")


class Match(UUIDTimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("event_id", "sequence"),
        UniqueConstraint("previous_match_id"),
        Index("ix_matches_event_started_at", "event_id", "started_at"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("pelada_events.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_match_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("matches.id"))
    advancing_team_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("event_teams.id")
    )
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status"),
        default=MatchStatus.SCHEDULED,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timer_elapsed_ms: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    timer_running_since: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    event: Mapped[PeladaEvent] = relationship(back_populates="matches")
    previous_match: Mapped[Optional[Match]] = relationship(
        back_populates="next_match", remote_side="Match.id"
    )
    next_match: Mapped[Optional[Match]] = relationship(
        back_populates="previous_match", uselist=False
    )
    teams: Mapped[list[MatchTeam]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    lineups: Mapped[list[MatchLineup]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    actions: Mapped[list[GameAction]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class MatchTeam(UUIDTimestampMixin, Base):
    """Resultado de um dos times em uma partida; a origem de vitórias e derrotas."""

    __tablename__ = "match_teams"
    __table_args__ = (UniqueConstraint("match_id", "team_id"),)

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("event_teams.id"), nullable=False)
    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[Optional[MatchResult]] = mapped_column(
        Enum(MatchResult, name="match_result")
    )

    match: Mapped[Match] = relationship(back_populates="teams")
    team: Mapped[EventTeam] = relationship(back_populates="match_entries")


class MatchLineup(UUIDTimestampMixin, Base):
    """Quem efetivamente jogou a partida, inclusive o goleiro para gols sofridos."""

    __tablename__ = "match_lineups"
    __table_args__ = (
        UniqueConstraint("match_id", "profile_id", name="uq_match_lineup_profile"),
        UniqueConstraint("match_id", "guest_id", name="uq_match_lineup_guest"),
        CheckConstraint(
            "(profile_id IS NOT NULL AND guest_id IS NULL) OR "
            "(profile_id IS NULL AND guest_id IS NOT NULL)",
            name="profile_or_guest_match_lineup",
        ),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("event_teams.id"), nullable=False)
    profile_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("profiles.id"))
    guest_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("group_guests.id", ondelete="CASCADE")
    )
    role: Mapped[TeamPlayerRole] = mapped_column(
        Enum(TeamPlayerRole, name="lineup_player_role"),
        default=TeamPlayerRole.PLAYER,
        nullable=False,
    )

    match: Mapped[Match] = relationship(back_populates="lineups")
    profile: Mapped[Profile] = relationship(back_populates="lineup_entries")
    guest: Mapped[Optional[GroupGuest]] = relationship(back_populates="lineup_entries")


class GameAction(UUIDTimestampMixin, Base):
    """Ocorrência individual durante o jogo; rankings são agregados desta tabela."""

    __tablename__ = "game_actions"
    __table_args__ = (
        Index("ix_game_actions_match_type", "match_id", "action_type"),
        CheckConstraint(
            "(player_id IS NOT NULL AND guest_id IS NULL) OR "
            "(player_id IS NULL AND guest_id IS NOT NULL)",
            name="profile_or_guest_game_action",
        ),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("event_teams.id"), nullable=False)
    player_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("profiles.id"))
    guest_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("group_guests.id", ondelete="CASCADE")
    )
    action_type: Mapped[GameActionType] = mapped_column(
        Enum(GameActionType, name="game_action_type"), nullable=False
    )
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    minute: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    match: Mapped[Match] = relationship(back_populates="actions")
    player: Mapped[Profile] = relationship(back_populates="game_actions")
    guest: Mapped[Optional[GroupGuest]] = relationship(back_populates="game_actions")
