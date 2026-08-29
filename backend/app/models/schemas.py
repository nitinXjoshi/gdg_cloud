"""Pydantic request/response schemas with strict validation.

All participant-supplied input is treated as untrusted and constrained here at
the API boundary. Schemas never expose internal prompts, flags, provider
credentials, or token hashes. Token usage is only reported when the provider
actually returned it; otherwise it is explicitly marked unavailable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionCreateRequest(BaseModel):
    """Request to mint a participant session. No credentials required by design."""

    model_config = ConfigDict(extra="forbid")


class SessionResponse(BaseModel):
    """Returned once at session creation — the raw token is never re-sent."""

    session_id: str
    api_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105


class AttemptRequest(BaseModel):
    """A single challenge attempt from a participant."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=120_000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=50)

    @field_validator("prompt")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty")
        if "\x00" in v:
            raise ValueError("prompt contains invalid characters")
        return v


class Usage(BaseModel):
    """Token usage as actually reported by the provider."""

    available: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AttemptResponse(BaseModel):
    request_id: str
    response: str
    challenge_solved: bool
    latency_ms: float
    usage: Usage
    model: str | None = None
    error: str | None = None


class ChallengeSummary(BaseModel):
    challenge_id: str
    name: str
    description: str
    difficulty: str
    enabled: bool
    model: str


class ChallengeDetail(ChallengeSummary):
    """Public detail — deliberately excludes the system prompt and flag."""

    max_output_tokens: int


class StatsResponse(BaseModel):
    total_attempts: int
    solved_attempts: int
    success_rate: float
    active_participants: int
    requests_per_minute: float
    total_input_tokens: int | None
    total_output_tokens: int | None
    usage_available: bool
    avg_latency_ms: float
    error_rate: float


class ComponentStatus(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    application: str
    environment: str
    provider: str
    database: str
    redis: str
    ollama: str
    model: str | None = None
    version: str


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
    code: str | None = None
