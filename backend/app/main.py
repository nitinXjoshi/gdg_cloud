"""PromptForge FastAPI application entrypoint.

Wires configuration, logging, middleware, database, challenge engine, provider,
and API routes together. The backend is stateless: all shared state lives in
PostgreSQL/Redis, so multiple instances can run behind a load balancer.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import create_rate_limiter
from app.api.routes import admin, challenge, health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.knowledge.loader import KnowledgeLoader
from app.middleware.error_handler import register_exception_handlers
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import (
    _security_headers_middleware,
    configure_cors,
)
from app.models.database import close_database, create_all, get_engine, init_database
from app.services.challenge_engine import ChallengeEngine
from app.services.llm.factory import get_provider


def _find_frontend_dir() -> Path:
    p2 = Path(__file__).resolve().parents[2] / "frontend"
    if p2.is_dir():
        return p2
    p1 = Path(__file__).resolve().parents[1] / "frontend"
    if p1.is_dir():
        return p1
    return p2


_FRONTEND_DIR = _find_frontend_dir()
logger = logging.getLogger("promptforge.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging("DEBUG" if settings.is_dev else "INFO")

    init_database(settings)
    if settings.database_url and settings.database_url.startswith("postgresql"):
        # Production path: apply versioned migrations against PostgreSQL.
        from alembic import command
        from alembic.config import Config as AlembicConfig

        alembic_cfg = AlembicConfig("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    else:
        # Local development/test: SQLite via create_all for convenience.
        await create_all()

    provider = get_provider(settings)
    knowledge_loader = KnowledgeLoader()
    knowledge = knowledge_loader.load()

    app.state.settings = settings
    app.state.provider = provider
    app.state.knowledge_loader = knowledge_loader
    app.state.db_engine = get_engine()
    app.state.challenge_engine = ChallengeEngine(provider, settings, knowledge=knowledge)
    app.state.rate_limiter = create_rate_limiter(settings)

    logger.info(
        "application started",
        extra={
            "environment": settings.environment,
            "provider": settings.llm_provider,
            "model": settings.ollama_model,
        },
    )
    yield

    await close_database()
    logger.info("application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("DEBUG" if settings.is_dev else "INFO")

    app = FastAPI(
        title="PromptForge",
        description="Adversarial LLM Sandbox — prompt-injection challenge platform",
        version="1.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_dev else None,
    )

    app.add_middleware(RequestIDMiddleware)
    configure_cors(app, settings.cors_origin_list)
    app.middleware("http")(_security_headers_middleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(challenge.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the static frontend if present (optional; API-only runs still work)."""
    if not _FRONTEND_DIR.is_dir():
        return
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.get("/admin", include_in_schema=False)
    async def admin_index() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "admin.html")


app = create_app()
