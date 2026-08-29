"""Async database engine/session management.

Uses PostgreSQL (``asyncpg``) in production and SQLite (``aiosqlite``) in
development/test when ``DATABASE_URL`` is unset. This keeps the entire project
runnable without any external services while preserving the production path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.db.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _default_database_url() -> str:
    return "sqlite+aiosqlite:///./promptforge.db"


def init_database(settings: Settings | None = None) -> None:
    """Create the async engine and session factory."""
    global _engine, _session_factory

    url = (settings.database_url if settings else None) or _default_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    _engine = create_async_engine(url, echo=False, pool_pre_ping=True, connect_args=connect_args)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


def get_engine():
    if _engine is None:
        init_database()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_database()
    return _session_factory  # type: ignore[return-value]


async def create_all() -> None:
    """Create tables (development convenience; use Alembic in production)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
