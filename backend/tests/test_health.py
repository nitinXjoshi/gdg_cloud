"""Tests for health checks and system status service."""

from __future__ import annotations

import pytest

from app.services.system_status import SystemStatus, check_database, check_redis


@pytest.mark.asyncio
async def test_health_endpoint_returns_real_structure(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Must contain real status for all core dependencies
    assert "application" in data
    assert data["application"] == "healthy"
    assert "database" in data
    assert data["database"] in {"healthy", "unavailable"}
    assert "redis" in data
    assert data["redis"] in {"healthy", "unavailable", "disabled"}
    assert "ollama" in data
    assert "model" in data
    assert "model_name" in data
    assert "version" in data

    # Must NEVER expose private server-side URLs, credentials, or keys
    assert "ollama_base_url" not in data
    assert "database_url" not in data
    assert "redis_url" not in data
    assert "admin_api_key" not in data
    assert "secret" not in data
    assert "flag" not in data


@pytest.mark.asyncio
async def test_check_database_healthy(client):
    from app.models.database import get_engine

    engine = get_engine()
    result = await check_database(engine)
    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_check_database_failure():
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("Database connection failure")

    result = await check_database(BrokenEngine())
    assert result["status"] == "unavailable"
    assert result["detail"] == "RuntimeError"


@pytest.mark.asyncio
async def test_check_redis_disabled():
    result = await check_redis(None)
    assert result["status"] == "disabled"
    assert "in-memory" in result["detail"]


@pytest.mark.asyncio
async def test_check_redis_failure():
    # Invalid redis port/host
    result = await check_redis("redis://127.0.0.1:9999/0")
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_system_status_snapshot_without_provider():
    class DummyApp:
        class State:
            settings = None
            db_engine = None

        state = State()

    from app.core.config import Settings
    from app.models.database import get_engine

    app = DummyApp()
    app.state.settings = Settings(environment="test")
    app.state.db_engine = get_engine()

    status = await SystemStatus(app).snapshot()
    assert status["application"] == "healthy"
    assert status["ollama"] == "unavailable"
