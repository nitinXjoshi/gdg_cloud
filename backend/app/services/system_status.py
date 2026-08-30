"""System status service: real health checks for DB, Redis, and Ollama.

Never returns "healthy" on assumption. Each check performs an actual operation
against the live dependency and reports its true state.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("promptforge.health")


async def check_database(engine) -> dict[str, str]:
    """Run a real ``SELECT 1`` against the database engine."""
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("database health check failed", extra={"error": exc.__class__.__name__})
        return {"status": "unavailable", "detail": exc.__class__.__name__}


async def check_redis(redis_url: str | None) -> dict[str, str]:
    """Ping Redis if configured; otherwise report the explicitly local fallback."""
    if not redis_url:
        return {"status": "disabled", "detail": "in-memory rate limiter (Redis not configured)"}

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url, decode_responses=True)
        pong = await client.ping()
        await client.aclose()
        if pong:
            return {"status": "healthy"}
        return {"status": "unavailable", "detail": "unexpected ping response"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis health check failed", extra={"error": exc.__class__.__name__})
        return {"status": "unavailable", "detail": exc.__class__.__name__}


class SystemStatus:
    """Aggregate real status for the /health and admin system-status views."""

    def __init__(self, app) -> None:
        self._app = app

    async def snapshot(self) -> dict[str, Any]:
        settings = self._app.state.settings
        engine = self._app.state.db_engine

        database = await check_database(engine)
        redis = await check_redis(settings.redis_url)

        provider = getattr(self._app.state, "provider", None)
        ollama = (
            await provider.health()
            if provider
            else {"status": "unavailable", "reason": "no provider"}
        )
        ollama_status = ollama.get("status", "unavailable")
        model_status = ollama.get("model", "unavailable") if ollama_status == "healthy" else None

        return {
            "application": "healthy",
            "environment": settings.environment,
            "provider": settings.llm_provider,
            "database": database["status"],
            "redis": redis["status"],
            "ollama": ollama_status,
            "model": model_status,
            "model_name": settings.ollama_model,
            "version": "1.1.0",
        }
