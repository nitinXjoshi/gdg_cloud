"""Vercel Serverless Function entrypoint for PromptForge FastAPI backend.

This entrypoint exports the ASGI `app` instance from `backend.app.main`
so that Vercel's `@vercel/python` runtime can execute API and health
requests in a serverless environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and backend directory to sys.path so 'app' and dependencies resolve
_root_dir = Path(__file__).resolve().parent.parent
_backend_dir = _root_dir / "backend"

for _path in (str(_root_dir), str(_backend_dir)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.main import app  # noqa: E402

__all__ = ["app"]
