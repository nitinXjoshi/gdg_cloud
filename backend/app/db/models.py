"""SQLAlchemy ORM models for participants, sessions, challenges, attempts, and
usage metrics.

Secrets and flags are never persisted. Participant API tokens are stored only
as SHA-256 hashes. Attempts do not store raw prompts unless ``STORE_PROMPTS`` is
explicitly enabled (off by default).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="participant")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    participant: Mapped[Participant] = relationship(back_populates="sessions")


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    # NOTE: The flag is intentionally NOT persisted. It is generated at runtime
    # and held only in the challenge engine's memory for the life of the process.
    difficulty: Mapped[str] = mapped_column(String(32), default="medium")
    model: Mapped[str] = mapped_column(String(64))
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    attempts: Mapped[list[Attempt]] = relationship(back_populates="challenge")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )
    challenge_id: Mapped[str] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    usage_available: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(32), default="ollama")
    model: Mapped[str] = mapped_column(String(64), default="")
    solved: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    challenge: Mapped[Challenge] = relationship(back_populates="attempts")


class UsageMetric(Base):
    """Rolling per-minute/aggregate usage used for cost control and dashboards."""

    __tablename__ = "usage_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bucket_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    solved: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    usage_available: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
