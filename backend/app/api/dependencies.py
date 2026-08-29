"""FastAPI dependencies for authentication, rate limiting, and admin auth.

Authentication is a lightweight bearer-token scheme: participants mint a token,
we store only its SHA-256 hash, and every attempt is associated with the
participant's session.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimitService
from app.core.security import hash_token, verify_token
from app.models.database import get_session
from app.repositories.challenge_repository import ParticipantRepository

logger = logging.getLogger("promptforge.auth")

_bearer = HTTPBearer(auto_error=False)


def _is_expired(expires_at: datetime) -> bool:
    """Safely compare a possibly-naive stored datetime against now (UTC)."""
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < now


async def get_current_participant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Resolve the bearer token to a participant ID, or 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token_hash = hash_token(credentials.credentials)
    repo = ParticipantRepository()
    db_session = await repo.get_session_by_token_hash(session, token_hash)
    if db_session is None or db_session.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if _is_expired(db_session.expires_at):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return db_session.participant_id


async def enforce_rate_limits(
    request: Request,
    participant_id: str = Depends(get_current_participant),
    settings: Settings = Depends(get_settings),
) -> str:
    """Apply per-participant and per-IP rate limits before a challenge attempt."""
    limiter: RateLimitService = request.app.state.rate_limiter
    client_ip = request.client.host if request.client else "unknown"

    participant_result = await limiter.check_participant(participant_id)
    if not participant_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Slow down.",
            headers={"Retry-After": str(int(participant_result.retry_after_seconds) + 1)},
        )

    ip_result = await limiter.check_ip(client_ip)
    if not ip_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this IP.",
            headers={"Retry-After": str(int(ip_result.retry_after_seconds) + 1)},
        )

    return participant_id


def require_admin(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate the ``X-Admin-Key`` header against the configured admin key."""
    # Prefer app-level settings so tests/DI can override the default config.
    effective = getattr(request.app.state, "settings", settings)
    supplied = request.headers.get("X-Admin-Key", "")
    if not supplied or not verify_token(supplied, hash_token(effective.admin_api_key)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )


def create_rate_limiter(settings: Settings) -> RateLimitService:
    """Build the configured rate limiter (Redis or in-memory)."""
    from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter

    if settings.redis_url:
        limiter = RedisRateLimiter(settings.redis_url)
    else:
        limiter = InMemoryRateLimiter()

    service = RateLimitService(limiter, settings.max_requests_per_minute)
    service.set_max_concurrent(settings.max_concurrent_requests)
    return service
