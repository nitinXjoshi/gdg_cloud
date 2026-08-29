"""Provider factory: build the configured LLM provider from settings.

The only supported runtime provider is Ollama. The factory caches a single
client per configuration so the HTTP connection pool is reused across requests.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.ollama_provider import OllamaProvider

_provider_cache: dict[tuple[str, str], LLMProvider] = {}


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured Ollama provider, reusing a client per config."""
    settings = settings or get_settings()
    cache_key = (settings.llm_provider, settings.ollama_model)

    if cache_key not in _provider_cache:
        _provider_cache[cache_key] = OllamaProvider(settings)

    return _provider_cache[cache_key]
