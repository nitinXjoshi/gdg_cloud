"""Centralized exception handling with safe error messages.

Production responses never include stack traces or internal state. Each error
maps to an appropriate HTTP status and a short ``code`` for client handling.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("promptforge.errors")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "http error",
        extra={
            "request_id": _request_id(request),
            "endpoint": request.url.path,
            "status_code": exc.status_code,
            "error": exc.detail,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": str(exc.detail),
            "request_id": _request_id(request),
            "code": "http_error",
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "request_id": _request_id(request),
            "code": "validation_error",
            # Include field errors (no secrets are present in validation input).
            "errors": exc.errors(),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log the exception type only; never the full stack in production responses.
    logger.error(
        "unhandled error",
        extra={
            "request_id": _request_id(request),
            "endpoint": request.url.path,
            "error": exc.__class__.__name__,
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": _request_id(request),
            "code": "internal_error",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
