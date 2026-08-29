"""Telemetry and metrics for attempts, latency, and token usage.

Aggregates are derived from the database (source of truth) rather than kept in a
second in-memory store, keeping the backend stateless. Token totals are only
reported when at least one attempt carried genuine usage data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricsSnapshot:
    total_attempts: int
    solved_attempts: int
    success_rate: float
    active_participants: int
    requests_per_minute: float
    total_input_tokens: int | None
    total_output_tokens: int | None
    usage_available: bool
    avg_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    errors: int


class TelemetryService:
    """Compute dashboard metrics from attempt records."""

    async def snapshot(self, attempts, participants_count: int) -> MetricsSnapshot:
        attempts = list(attempts)
        total = len(attempts)
        solved = sum(1 for a in attempts if a.solved)
        errors = sum(1 for a in attempts if a.error)

        usage_attempts = [a for a in attempts if a.usage_available]
        usage_available = bool(usage_attempts)
        total_input = (
            sum(a.input_tokens for a in usage_attempts if a.input_tokens is not None)
            if usage_available
            else None
        )
        total_output = (
            sum(a.output_tokens for a in usage_attempts if a.output_tokens is not None)
            if usage_available
            else None
        )

        latencies = sorted(a.latency_ms for a in attempts if a.latency_ms is not None)
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        p95_latency = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0

        return MetricsSnapshot(
            total_attempts=total,
            solved_attempts=solved,
            success_rate=round(solved / total, 4) if total else 0.0,
            active_participants=participants_count,
            requests_per_minute=0.0,  # computed by the route from a time window
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            usage_available=usage_available,
            avg_latency_ms=round(avg_latency, 2),
            p95_latency_ms=round(p95_latency, 2),
            error_rate=round(errors / total, 4) if total else 0.0,
            errors=errors,
        )
