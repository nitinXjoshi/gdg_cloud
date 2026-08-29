"""Public challenge API: session minting, challenge metadata, attempts, and stats."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import enforce_rate_limits
from app.core.config import Settings, get_settings
from app.models.database import get_session
from app.models.schemas import (
    AttemptRequest,
    AttemptResponse,
    ChallengeDetail,
    ChallengeSummary,
    SessionCreateRequest,
    SessionResponse,
    StatsResponse,
    Usage,
)
from app.repositories.attempt_repository import AttemptRepository, UsageRepository
from app.repositories.challenge_repository import ParticipantRepository
from app.services.llm.base import LLMUnavailableError
from app.services.telemetry import TelemetryService

logger = logging.getLogger("promptforge.challenge")

router = APIRouter()


@router.post(
    "/auth/session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
async def create_session(
    _body: SessionCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    """Mint a participant session and return its bearer token exactly once."""
    repo = ParticipantRepository()
    participant = await repo.create_participant(session)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    db_session, raw_token = await repo.create_session(session, participant, expires_at=expires_at)
    await session.commit()

    logger.info(
        "session created",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "participant_id": participant.id,
            "endpoint": request.url.path,
        },
    )
    return SessionResponse(session_id=db_session.id, api_token=raw_token)


@router.get("/challenges", response_model=list[ChallengeSummary], tags=["challenges"])
async def list_challenges(request: Request) -> list[ChallengeSummary]:
    engine = request.app.state.challenge_engine
    return [c.to_summary() for c in engine.list_challenges()]


@router.get(
    "/challenges/{challenge_id}",
    response_model=ChallengeDetail,
    tags=["challenges"],
)
async def get_challenge(challenge_id: str, request: Request) -> ChallengeDetail:
    engine = request.app.state.challenge_engine
    challenge = engine.get_challenge(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return challenge.to_detail()


@router.post(
    "/challenges/{challenge_id}/attempt",
    response_model=AttemptResponse,
    tags=["challenges"],
)
async def attempt_challenge(
    challenge_id: str,
    body: AttemptRequest,
    request: Request,
    participant_id: str = Depends(enforce_rate_limits),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AttemptResponse:
    """Run one prompt-injection attempt against the challenge.

    Validates size, applies rate limits, delegates to the challenge engine, and
    persists telemetry. The hidden flag and system prompt are never returned.
    """
    engine = request.app.state.challenge_engine

    if not engine.challenge_exists(challenge_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")

    if len(body.prompt) > settings.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Prompt exceeds maximum allowed length",
        )

    # Concurrency guard: reject if too many in-flight LLM calls.
    limiter = request.app.state.rate_limiter
    acquired = await limiter.acquire_concurrency()
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent requests",
        )

    try:
        result = await engine.run_attempt(
            challenge_id,
            body.prompt,
            participant_id=participant_id,
            history=body.history,
        )
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    finally:
        await limiter.release_concurrency()

    attempt_repo = AttemptRepository()
    await attempt_repo.create(
        session,
        request_id=result.request_id,
        participant_id=participant_id,
        challenge_id=challenge_id,
        result=result,
        store_prompt=settings.store_prompts,
        prompt_text=body.prompt if settings.store_prompts else None,
    )

    usage_repo = UsageRepository()
    await usage_repo.record(
        session,
        result=result,
        solved=result.challenge_solved,
        is_error=result.error is not None,
    )
    await session.commit()

    logger.info(
        "attempt completed",
        extra={
            "request_id": result.request_id,
            "endpoint": request.url.path,
            "participant_id": participant_id,
            "challenge_id": challenge_id,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": round(result.latency_ms, 2),
            "tokens": {
                "available": result.usage_available,
                "input": result.input_tokens,
                "output": result.output_tokens,
                "total": result.total_tokens,
            },
            "challenge_solved": result.challenge_solved,
            "error": result.error,
        },
    )

    return AttemptResponse(
        request_id=result.request_id,
        response=result.response,
        challenge_solved=result.challenge_solved,
        latency_ms=round(result.latency_ms, 2),
        usage=Usage(
            available=result.usage_available,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
        ),
        model=result.model,
        error=result.error,
    )


@router.get("/stats", response_model=StatsResponse, tags=["stats"])
async def get_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    attempts = await AttemptRepository().list_all(session)
    participants = await ParticipantRepository().count(session)
    snapshot = await TelemetryService().snapshot(attempts, participants)

    # Requests per minute over the trailing 60s window.
    since = datetime.now(UTC) - timedelta(seconds=60)
    rpm = await AttemptRepository().count_since(session, since)

    return StatsResponse(
        total_attempts=snapshot.total_attempts,
        solved_attempts=snapshot.solved_attempts,
        success_rate=snapshot.success_rate,
        active_participants=snapshot.active_participants,
        requests_per_minute=float(rpm),
        total_input_tokens=snapshot.total_input_tokens,
        total_output_tokens=snapshot.total_output_tokens,
        usage_available=snapshot.usage_available,
        avg_latency_ms=snapshot.avg_latency_ms,
        error_rate=snapshot.error_rate,
    )
