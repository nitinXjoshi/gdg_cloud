"""Rate limiting with a Redis backend and an in-memory fallback.

The limiter is intentionally minimal and dependency-injected so unit tests never
need a running Redis instance. Redis is used when available for cross-instance
consistency behind a load balancer; otherwise an in-memory implementation keeps
local development and tests fully functional.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: float = 0.0


class RateLimiter(ABC):
    """Abstract rate-limiter contract."""

    @abstractmethod
    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: float = 60.0,
    ) -> RateLimitResult:
        """Check whether ``key`` is allowed ``limit`` calls per ``window_seconds``."""


class InMemoryRateLimiter(RateLimiter):
    """Sliding-window limiter backed by process memory. Not shared across instances."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: float = 60.0,
    ) -> RateLimitResult:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]

        if len(hits) >= limit:
            oldest = hits[0]
            retry_after = max(0.0, window_seconds - (now - oldest))
            self._hits[key] = hits
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=retry_after,
            )

        hits.append(now)
        self._hits[key] = hits
        return RateLimitResult(allowed=True, remaining=limit - len(hits))


class RedisRateLimiter(RateLimiter):
    """Fixed-window limiter backed by Redis using a Lua script for atomicity."""

    _SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('TTL', KEYS[1])
    if ttl < 0 then ttl = 0 end
    return {current, ttl}
    """

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: float = 60.0,
    ) -> RateLimitResult:
        current, ttl = await self._redis.eval(
            self._SCRIPT,
            1,
            f"rl:{key}",
            str(int(window_seconds)),
        )
        current, ttl = int(current), int(ttl)
        if current > limit:
            return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=ttl)
        return RateLimitResult(allowed=True, remaining=limit - current)

    async def close(self) -> None:
        await self._redis.aclose()


class RateLimitService:
    """High-level rate limits for participants, IPs, and global concurrency."""

    def __init__(self, limiter: RateLimiter, max_requests_per_minute: int) -> None:
        self._limiter = limiter
        self._max_rpm = max_requests_per_minute
        self._semaphore: asyncio.Semaphore | None = None
        self._max_concurrent = 10

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = value
        self._semaphore = asyncio.Semaphore(value)

    async def check_participant(self, participant_id: str) -> RateLimitResult:
        return await self._limiter.check(
            f"participant:{participant_id}",
            self._max_rpm,
            window_seconds=60.0,
        )

    async def check_ip(self, ip: str) -> RateLimitResult:
        # IPs get a slightly higher ceiling to tolerate shared NAT, but still bounded.
        return await self._limiter.check(
            f"ip:{ip}",
            max(self._max_rpm * 3, 60),
            window_seconds=60.0,
        )

    async def acquire_concurrency(self) -> bool:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return await self._semaphore.acquire()

    async def release_concurrency(self) -> None:
        if self._semaphore is not None:
            self._semaphore.release()
