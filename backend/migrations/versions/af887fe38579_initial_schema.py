"""initial schema

Revision ID: af887fe38579
Revises:
Create Date: 2026-08-29 20:52:04.695598
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "af887fe38579"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_sessions_participant_id", "sessions", ["participant_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)

    op.create_table(
        "challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "challenge_id",
            sa.String(36),
            sa.ForeignKey("challenges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("usage_available", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_cents", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("solved", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(120), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
    )
    op.create_index("ix_attempts_request_id", "attempts", ["request_id"], unique=True)
    op.create_index("ix_attempts_participant_id", "attempts", ["participant_id"])
    op.create_index("ix_attempts_challenge_id", "attempts", ["challenge_id"])

    op.create_table(
        "usage_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bucket_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("solved", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("usage_available", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
    )
    op.create_index("ix_usage_metrics_bucket_ts", "usage_metrics", ["bucket_ts"])


def downgrade() -> None:
    op.drop_table("usage_metrics")
    op.drop_table("attempts")
    op.drop_table("challenges")
    op.drop_table("sessions")
    op.drop_table("participants")
