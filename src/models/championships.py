"""Times permanentes e edições de campeonatos, fora do CRUD público."""
from uuid import UUID
from datetime import datetime
from sqlalchemy import Boolean, DateTime, CheckConstraint, ForeignKey, FetchedValue, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from src.models.base import Base, UUIDTimestampMixin


class Club(UUIDTimestampMixin, Base):
    __tablename__ = "clubs"
    name: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))


class ClubMember(UUIDTimestampMixin, Base):
    __tablename__ = "club_members"
    __table_args__ = (UniqueConstraint("club_id", "profile_id"),
                     CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="club_member_status"))
    club_id: Mapped[UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Championship(UUIDTimestampMixin, Base):
    __tablename__ = "championships"
    __table_args__ = (
        UniqueConstraint("code", name="championships_code_unique"),
        CheckConstraint("capacity IN (4, 8, 16)", name="championship_capacity"),
        CheckConstraint("format <> 'cascade' OR capacity = 4", name="cascade_four_teams"),
        CheckConstraint("format IN ('groups_knockout', 'knockout', 'cascade')", name="championship_format"),
        CheckConstraint("status IN ('registration', 'in_progress', 'finished')", name="championship_status"),
    )
    code: Mapped[str] = mapped_column(String(6), server_default=FetchedValue(), nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    season: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))
    format: Mapped[str] = mapped_column(String(24))
    capacity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="registration")
    champion_id: Mapped[UUID | None] = mapped_column(ForeignKey("clubs.id"))


class ChampionshipEntry(UUIDTimestampMixin, Base):
    __tablename__ = "championship_entries"
    __table_args__ = (UniqueConstraint("championship_id", "club_id"),)
    championship_id: Mapped[UUID] = mapped_column(ForeignKey("championships.id", ondelete="CASCADE"))
    club_id: Mapped[UUID] = mapped_column(ForeignKey("clubs.id"))
    seed: Mapped[int] = mapped_column(Integer)


class ChampionshipPlayer(UUIDTimestampMixin, Base):
    __tablename__ = "championship_players"
    __table_args__ = (UniqueConstraint("championship_id", "profile_id"),)
    championship_id: Mapped[UUID] = mapped_column(ForeignKey("championships.id", ondelete="CASCADE"))
    entry_id: Mapped[UUID] = mapped_column(ForeignKey("championship_entries.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))


class ChampionshipMatch(UUIDTimestampMixin, Base):
    __tablename__ = "championship_matches"
    __table_args__ = (UniqueConstraint("championship_id", "sequence"),
                     CheckConstraint("home_id <> away_id", name="different_clubs"),
                     CheckConstraint("home_score >= 0 AND away_score >= 0", name="positive_scores"))
    championship_id: Mapped[UUID] = mapped_column(ForeignKey("championships.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(16))
    round: Mapped[int] = mapped_column(Integer)
    pool: Mapped[str | None] = mapped_column(String(1))
    home_id: Mapped[UUID] = mapped_column(ForeignKey("clubs.id"))
    away_id: Mapped[UUID] = mapped_column(ForeignKey("clubs.id"))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    winner_id: Mapped[UUID | None] = mapped_column(ForeignKey("clubs.id"))
    statistics_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    actions: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))


class ChampionshipStatistic(UUIDTimestampMixin, Base):
    __tablename__ = "championship_statistics"
    __table_args__ = (UniqueConstraint("match_id", "profile_id"),
                     CheckConstraint("goals >= 0 AND assists >= 0 AND own_goals >= 0", name="nonnegative_statistics"))
    match_id: Mapped[UUID] = mapped_column(ForeignKey("championship_matches.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    own_goals: Mapped[int] = mapped_column(Integer, default=0)


class ChampionshipTrophy(UUIDTimestampMixin, Base):
    __tablename__ = "championship_trophies"
    __table_args__ = (UniqueConstraint("championship_id", "profile_id", "category"),)
    championship_id: Mapped[UUID] = mapped_column(ForeignKey("championships.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(350))
    value: Mapped[int] = mapped_column(Integer)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
