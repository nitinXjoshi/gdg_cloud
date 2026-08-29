"""Application configuration.

All values come from environment variables (optionally a `.env` file) so that
credentials and tunables are never hardcoded. ``BaseSettings`` from
``pydantic-settings`` handles coercion, validation, and defaults.

The only supported LLM provider at runtime is **Ollama** (a real local model).
There is no mock provider and no paid cloud provider in the runtime path.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PromptForge settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---
    environment: Literal["development", "test", "production"] = "development"

    # --- LLM provider (Ollama only) ---
    llm_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 120.0

    # --- Database ---
    database_url: str | None = None

    # --- Redis ---
    redis_url: str | None = None

    # --- Admin ---
    admin_api_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))

    # --- Safety controls ---
    max_prompt_length: int = 12_000
    max_output_tokens: int = 1_024
    max_requests_per_minute: int = 20
    max_concurrent_requests: int = 10

    # --- LLM resilience ---
    llm_max_retries: int = 1

    # --- Misc ---
    store_prompts: bool = False
    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,http://localhost:8000,"
        "http://127.0.0.1:8000,https://gdg-cloud.vercel.app"
    )

    @field_validator("admin_api_key", mode="before")
    @classmethod
    def _coerce_admin_key(cls, v: str | None) -> str:
        if not v:
            return secrets.token_urlsafe(48)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.environment in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (dependency-injected where possible)."""
    return Settings()
