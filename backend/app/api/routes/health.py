"""Health check endpoint with real component checks."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.system_status import SystemStatus

router = APIRouter()


@router.get("/health", tags=["system"])
async def health(request: Request) -> dict:
    """Report actual status for FastAPI, PostgreSQL, Redis, and Ollama."""
    return await SystemStatus(request.app).snapshot()
