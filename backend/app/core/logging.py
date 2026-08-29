"""Structured JSON logging.

Every log line is a single JSON object with a ``request_id`` when available.
This module intentionally avoids logging secrets, API keys, raw system prompts,
and authentication tokens — see ``secret_detector.py`` and call sites.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

# Keys that must never appear in structured logs. Values are redacted if a key
# (case-insensitive) contains any of these substrings.
_SENSITIVE_KEY_MARKERS = (
    "secret",
    "flag",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "password",
    "system_prompt",
    "credential",
)


def _redact(obj: Any, *, depth: int = 0) -> Any:
    """Recursively redact sensitive values from a log payload."""
    if depth > 8:
        return REDACTED

    if isinstance(obj, dict):
        return {
            k: (
                REDACTED
                if any(m in k.lower() for m in _SENSITIVE_KEY_MARKERS)
                else _redact(v, depth=depth + 1)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list | tuple):
        return [_redact(v, depth=depth + 1) for v in obj]
    return obj


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with automatic redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for attr in (
            "request_id",
            "endpoint",
            "method",
            "status_code",
            "latency_ms",
            "participant_id",
            "challenge_id",
            "provider",
            "model",
            "tokens",
            "error",
            "challenge_solved",
        ):
            value = getattr(record, attr, None)
            if value is not None:
                payload[attr] = value

        # Include any explicit extra fields, redacted.
        extra = getattr(record, "log_extra", None)
        if isinstance(extra, dict):
            payload.update(_redact(extra))

        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with the JSON formatter."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Keep uvicorn access logs readable and JSON-consistent.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger whose records carry request context via ``extra``."""
    return logging.getLogger(name)
