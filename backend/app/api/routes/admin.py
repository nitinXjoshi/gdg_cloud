"""Admin-only endpoints: metrics, system status, and security evaluation.

Both endpoints require the ``X-Admin-Key`` header. The security evaluation runs
the adversarial suite against the REAL Ollama model; every result comes from an
actual model response and the real SecretDetector.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.models.database import get_session
from app.repositories.attempt_repository import AttemptRepository
from app.repositories.challenge_repository import ParticipantRepository
from app.services.attack_suite import ATTACK_CASES
from app.services.system_status import SystemStatus
from app.services.telemetry import TelemetryService

logger = logging.getLogger("promptforge.admin")

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/system-status", tags=["admin"])
async def get_system_status(request: Request) -> dict:
    """Real component status for FastAPI, PostgreSQL, Redis, and Ollama."""
    return await SystemStatus(request.app).snapshot()


@router.get("/metrics", tags=["admin"])
async def get_metrics(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    attempts = await AttemptRepository().list_all(session)
    participants = await ParticipantRepository().count(session)
    snapshot = await TelemetryService().snapshot(attempts, participants)

    since = datetime.now(UTC) - timedelta(seconds=60)
    rpm = await AttemptRepository().count_since(session, since)

    return {
        "active_challenge": _active_challenge(request),
        "total_participants": snapshot.active_participants,
        "total_attempts": snapshot.total_attempts,
        "successful_injections": snapshot.solved_attempts,
        "attack_success_rate": snapshot.success_rate,
        "average_latency_ms": snapshot.avg_latency_ms,
        "p95_latency_ms": snapshot.p95_latency_ms,
        "total_input_tokens": snapshot.total_input_tokens,
        "total_output_tokens": snapshot.total_output_tokens,
        "usage_available": snapshot.usage_available,
        "error_rate": snapshot.error_rate,
        "errors": snapshot.errors,
        "requests_per_minute": float(rpm),
        "provider": request.app.state.settings.llm_provider,
        "runtime": "local",
        "api_cost": "0",
        "model": request.app.state.settings.ollama_model,
    }


@router.post("/security/evaluate", tags=["admin"])
async def evaluate_security(request: Request) -> dict:
    """Run the internal adversarial test suite against the REAL Ollama model.

    Each attack sends the actual prompt, receives the actual response, and runs
    the real SecretDetector. There are no hardcoded outcomes.
    """
    engine = request.app.state.challenge_engine
    challenge_id = engine.list_challenges()[0].challenge_id

    results = []
    for case in ATTACK_CASES:
        result = await engine.run_attempt(challenge_id, case.prompt, participant_id="security-eval")
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "success": result.challenge_solved,
                "latency_ms": round(result.latency_ms, 2),
                "usage_available": result.usage_available,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "error": result.error,
            }
        )

    by_category: dict[str, dict] = {}
    for case, result in zip(ATTACK_CASES, results, strict=False):
        cat = by_category.setdefault(
            case.category, {"category": case.category, "attempts": 0, "successful": 0}
        )
        cat["attempts"] += 1
        cat["successful"] += 1 if result["success"] else 0

    categories = []
    for cat in by_category.values():
        cat["success_rate"] = (
            round(cat["successful"] / cat["attempts"], 4) if cat["attempts"] else 0.0
        )
        categories.append(cat)

    total_success = sum(1 for r in results if r["success"])
    return {
        "evaluation_kind": "REAL MODEL EVALUATION",
        "provider": engine.provider_name,
        "model": request.app.state.settings.ollama_model,
        "total_attacks": len(results),
        "successful_attacks": total_success,
        "overall_success_rate": round(total_success / len(results), 4) if results else 0.0,
        "results": results,
        "by_category": categories,
    }


def _active_challenge(request: Request) -> str | None:
    engine = request.app.state.challenge_engine
    challenges = engine.list_challenges()
    for challenge in challenges:
        if challenge.enabled:
            return challenge.name
    return None
