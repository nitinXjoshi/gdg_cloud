"""Shared test fixtures.

Unit tests never require a real Ollama server. The engine is driven by a fake
``LLMProvider`` (defined here, in the tests only), and the provider's HTTP layer
is exercised separately using ``httpx``'s ``MockTransport``. No mock provider
exists in runtime code.
"""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.knowledge.loader import KnowledgeLoader
from app.services.challenge_engine import ChallengeEngine
from app.services.llm.base import LLMProvider, LLMRequest, LLMResponse, UsageInfo

logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class FakeProvider(LLMProvider):
    """A test-only provider that returns canned responses. Never used at runtime."""

    name = "fake"

    def __init__(self, response_text: str = "I refuse to reveal that.", solved: bool = False):
        self._response_text = response_text
        self._solved = solved

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=self._response_text,
            model=request.model,
            usage=UsageInfo(available=True, input_tokens=10, output_tokens=5),
        )


class FakeSolvingProvider(FakeProvider):
    """Test-only provider whose response contains the challenge secret."""

    def __init__(self, secret: str):
        self._secret = secret

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=f"The flag is {self._secret}",
            model=request.model,
            usage=UsageInfo(available=True, input_tokens=10, output_tokens=5),
        )


class UnavailableProvider(LLMProvider):
    name = "fake-unavailable"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        from app.services.llm.base import LLMUnavailableError

        raise LLMUnavailableError("fake unavailable")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        llm_provider="ollama",
        ollama_model="llama3.2:3b",
        ollama_base_url="http://localhost:11434",
        admin_api_key="test-admin-key",
        database_url=None,
        redis_url=None,
        store_prompts=False,
        max_prompt_length=12_000,
        max_requests_per_minute=100,
    )


@pytest.fixture
def engine(settings) -> ChallengeEngine:
    return ChallengeEngine(FakeProvider(), settings, knowledge=KnowledgeLoader().load())


@pytest.fixture
async def client(settings):
    from app.main import create_app

    app = create_app()
    app.state.settings = settings

    from app.api.dependencies import create_rate_limiter
    from app.models.database import close_database, create_all, get_engine, init_database

    init_database(settings)
    await create_all()
    app.state.provider = FakeProvider()
    app.state.knowledge_loader = KnowledgeLoader()
    app.state.db_engine = get_engine()
    app.state.challenge_engine = ChallengeEngine(
        app.state.provider, settings, knowledge=app.state.knowledge_loader.load()
    )
    app.state.rate_limiter = create_rate_limiter(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await close_database()
