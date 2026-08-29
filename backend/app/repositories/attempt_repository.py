"""Repository for attempt records and usage metrics.

Stores real application telemetry only. Token usage is persisted only when the
provider actually reported it; otherwise it stays NULL.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attempt, UsageMetric


class AttemptRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        request_id: str,
        participant_id: str,
        challenge_id: str,
        result,
        store_prompt: bool,
        prompt_text: str | None,
    ) -> Attempt:
        attempt = Attempt(
            request_id=request_id,
            participant_id=participant_id,
            challenge_id=challenge_id,
            latency_ms=result.latency_ms,
            usage_available=result.usage_available,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            estimated_cost_cents=result.estimated_cost_cents,
            provider=result.provider,
            model=result.model,
            solved=result.challenge_solved,
            error=result.error,
            prompt_text=prompt_text if store_prompt else None,
        )
        session.add(attempt)
        await session.flush()
        return attempt

    async def list_all(self, session: AsyncSession) -> list[Attempt]:
        result = await session.execute(select(Attempt).order_by(Attempt.timestamp.desc()))
        return list(result.scalars())

    async def count_since(self, session: AsyncSession, since: datetime) -> int:
        result = await session.execute(
            select(func.count(Attempt.id)).where(Attempt.timestamp >= since)
        )
        return result.scalar_one()

    async def get_by_request_id(self, session: AsyncSession, request_id: str) -> Attempt | None:
        result = await session.execute(select(Attempt).where(Attempt.request_id == request_id))
        return result.scalar_one_or_none()


class UsageRepository:
    async def record(
        self,
        session: AsyncSession,
        *,
        result,
        solved: bool,
        is_error: bool,
    ) -> None:
        now = datetime.now(UTC)
        bucket = now.replace(second=0, microsecond=0)
        row = await session.execute(select(UsageMetric).where(UsageMetric.bucket_ts == bucket))
        metric = row.scalar_one_or_none()
        if metric is None:
            metric = UsageMetric(
                bucket_ts=bucket,
                attempts=0,
                solved=0,
                errors=0,
                usage_available=False,
                input_tokens=None,
                output_tokens=None,
                total_latency_ms=0.0,
            )
            session.add(metric)

        metric.attempts += 1
        metric.solved += 1 if solved else 0
        metric.errors += 1 if is_error else 0
        metric.usage_available = metric.usage_available or result.usage_available
        if result.input_tokens is not None:
            metric.input_tokens = (metric.input_tokens or 0) + result.input_tokens
        if result.output_tokens is not None:
            metric.output_tokens = (metric.output_tokens or 0) + result.output_tokens
        metric.total_latency_ms += result.latency_ms
        await session.flush()
