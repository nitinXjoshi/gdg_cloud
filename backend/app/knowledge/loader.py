"""Knowledge base loader.

Loads the authoritative ``HACKATHON_INTELLIGENCE.md`` file at application
startup and holds its content in memory. This content is sensitive internal
application configuration and must never be:

- exposed through public API endpoints
- included in OpenAPI schemas
- served as a static asset
- written to logs
- stored in PostgreSQL
- sent to the frontend

It is only made available to the internal prompt-construction layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("promptforge.knowledge")

# Resolved relative to this file so it works regardless of the process CWD.
_KNOWLEDGE_PATH = Path(__file__).resolve().parent / "HACKATHON_INTELLIGENCE.md"


class KnowledgeLoadError(RuntimeError):
    """Raised when the authoritative knowledge file cannot be loaded."""


class KnowledgeLoader:
    """Loads and holds the in-memory knowledge context."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _KNOWLEDGE_PATH
        self._content: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_loaded(self) -> bool:
        return self._content is not None

    @property
    def content(self) -> str:
        """Return the loaded knowledge content. Raises if not loaded."""
        if self._content is None:
            raise KnowledgeLoadError("Knowledge base has not been loaded")
        return self._content

    def load(self) -> str:
        """Read and validate the knowledge file into memory.

        Returns the loaded content and stores it for reuse. Raises
        ``KnowledgeLoadError`` if the file is missing, unreadable, or empty.
        """
        if not self._path.exists():
            raise KnowledgeLoadError(f"Knowledge file not found: {self._path}")

        if not self._path.is_file():
            raise KnowledgeLoadError(f"Knowledge path is not a file: {self._path}")

        try:
            content = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeLoadError(f"Failed to read knowledge file: {exc}") from exc

        if not content.strip():
            raise KnowledgeLoadError(f"Knowledge file is empty: {self._path}")

        self._content = content
        # Log only safe metadata — never the content itself.
        logger.info(
            "knowledge base loaded",
            extra={"path": str(self._path), "size_bytes": len(content.encode("utf-8"))},
        )
        return content
