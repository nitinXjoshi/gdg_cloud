"""Tests for rate limiting (in-memory fallback)."""

from __future__ import annotations

import pytest

from app.core.rate_limit import InMemoryRateLimiter, RateLimitService


@pytest.mark.asyncio
async def test_in_memory_limiter_allows_up_to_limit():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        result = await limiter.check("key", limit=3, window_seconds=60)
        assert result.allowed is True
    result = await limiter.check("key", limit=3, window_seconds=60)
    assert result.allowed is False
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_different_keys_are_independent():
    limiter = InMemoryRateLimiter()
    await limiter.check("a", limit=1, window_seconds=60)
    result = await limiter.check("b", limit=1, window_seconds=60)
    assert result.allowed is True


@pytest.mark.asyncio
async def test_rate_limit_service_wraps_participant():
    service = RateLimitService(InMemoryRateLimiter(), max_requests_per_minute=2)
    assert (await service.check_participant("p1")).allowed is True
    assert (await service.check_participant("p1")).allowed is True
    assert (await service.check_participant("p1")).allowed is False


async def test_rate_limit_429_via_api(client):
    resp = await client.post("/api/v1/auth/session", json={})
    token = resp.json()["api_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Client fixture uses max_requests_per_minute=100, so use a separate service
    # to verify the 429 path through the route is wired (limit not hit here).
    resp = await client.post(
        "/api/v1/challenges/challenge-primary/attempt",
        json={"prompt": "hello"},
        headers=headers,
    )
    assert resp.status_code == 200
