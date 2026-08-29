"""Security-related tests: authentication, authorization, and provider behavior.

Provider behavior is tested with ``httpx.MockTransport`` — HTTP is mocked, but
the OllamaProvider parsing logic under test is the real runtime code.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.services.llm.base import LLMError, LLMTimeoutError, LLMUnavailableError
from app.services.llm.ollama_provider import OllamaProvider


async def test_admin_endpoint_requires_key(client):
    resp = await client.get("/api/v1/admin/metrics")
    assert resp.status_code == 401


async def test_admin_endpoint_with_bad_key(client):
    resp = await client.get("/api/v1/admin/metrics", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 401


async def test_admin_endpoint_with_valid_key(client):
    resp = await client.get("/api/v1/admin/metrics", headers={"X-Admin-Key": "test-admin-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert "total_attempts" in body
    assert "attack_success_rate" in body
    assert body["runtime"] == "local"
    assert body["api_cost"] == "0"


async def test_security_evaluation_requires_admin(client):
    resp = await client.post("/api/v1/admin/security/evaluate")
    assert resp.status_code == 401


async def test_security_evaluation_runs(client):
    resp = await client.post(
        "/api/v1/admin/security/evaluate",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluation_kind"] == "REAL MODEL EVALUATION"
    assert body["total_attacks"] > 0
    assert "by_category" in body


def _settings(**overrides) -> Settings:
    return Settings(environment="test", llm_provider="ollama", **overrides)


def _ollama(handler, **overrides) -> OllamaProvider:
    settings = _settings(**overrides)
    return OllamaProvider(settings, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_ollama_provider_parses_real_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "llama3.2:3b",
                "message": {"role": "assistant", "content": "Hello world."},
                "prompt_eval_count": 36,
                "eval_count": 4,
            },
        )

    provider = _ollama(handler)
    from app.services.llm.base import LLMRequest

    response = await provider.complete(
        LLMRequest(
            system_prompt="sys",
            user_prompt="user",
            model="llama3.2:3b",
            max_output_tokens=100,
        )
    )
    assert response.text == "Hello world."
    assert response.usage.available is True
    assert response.usage.input_tokens == 36
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 40


@pytest.mark.asyncio
async def test_ollama_provider_marks_usage_unavailable_when_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "llama3.2:3b",
                "message": {"role": "assistant", "content": "Hi."},
            },
        )

    provider = _ollama(handler)
    from app.services.llm.base import LLMRequest

    response = await provider.complete(
        LLMRequest(system_prompt="s", user_prompt="u", model="m", max_output_tokens=10)
    )
    assert response.usage.available is False
    assert response.usage.input_tokens is None


@pytest.mark.asyncio
async def test_ollama_provider_model_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    provider = _ollama(handler)
    from app.services.llm.base import LLMRequest

    with pytest.raises(LLMUnavailableError):
        await provider.complete(
            LLMRequest(system_prompt="s", user_prompt="u", model="m", max_output_tokens=10)
        )


def test_timeout_error_type_exists():
    err = LLMTimeoutError("timeout")
    assert isinstance(err, LLMError)
