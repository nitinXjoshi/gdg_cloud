"""Unit tests for OllamaProvider: HTTP mock transport, timeouts, failures, malformed responses."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.services.llm.base import (
    LLMError,
    LLMRequest,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.ollama_provider import OllamaProvider


def _make_provider(handler, **overrides) -> OllamaProvider:
    defaults = {
        "environment": "test",
        "llm_provider": "ollama",
        "ollama_base_url": "http://mock-ollama:11434",
        "ollama_model": "llama3.2:3b",
        "ollama_timeout_seconds": 2.0,
        "llm_max_retries": 1,
    }
    defaults.update(overrides)
    settings = Settings(**defaults)
    return OllamaProvider(settings, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_ollama_provider_successful_completion():
    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_request["url"] = str(request.url)
        captured_request["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "model": "llama3.2:3b",
                "message": {"role": "assistant", "content": "Here is the response."},
                "prompt_eval_count": 50,
                "eval_count": 25,
            },
        )

    provider = _make_provider(handler)
    req = LLMRequest(
        system_prompt="System instructions",
        user_prompt="Hello assistant",
        model="llama3.2:3b",
        max_output_tokens=256,
        temperature=0.0,
        history=[{"role": "assistant", "content": "Prior message"}],
    )

    response = await provider.complete(req)

    assert response.text == "Here is the response."
    assert response.usage.available is True
    assert response.usage.input_tokens == 50
    assert response.usage.output_tokens == 25
    assert response.usage.total_tokens == 75

    # Verify message construction and user/system separation
    body = captured_request["body"]
    assert body["stream"] is False
    assert body["options"]["num_predict"] == 256
    messages = body["messages"]
    assert messages[0] == {"role": "system", "content": "System instructions"}
    assert messages[1] == {"role": "assistant", "content": "Prior message"}
    assert messages[2] == {"role": "user", "content": "Hello assistant"}


@pytest.mark.asyncio
async def test_ollama_provider_timeout_raises_llm_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMTimeoutError, match="timed out"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_connection_failure_raises_llm_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMUnavailableError, match="unreachable"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_malformed_json_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Not a valid JSON {{{")

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMError, match="malformed response"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_empty_content_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "   "}})

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMError, match="malformed response"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_non_dict_json_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "array"])

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMError, match="malformed response"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_500_status_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    provider = _make_provider(handler, llm_max_retries=0)
    req = LLMRequest(
        system_prompt="sys",
        user_prompt="user",
        model="llama3.2:3b",
        max_output_tokens=100,
    )

    with pytest.raises(LLMError, match="500"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_provider_health_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.3.14"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "llama3.2:3b"}, {"name": "mistral:latest"}]},
            )
        return httpx.Response(404)

    provider = _make_provider(handler)
    health = await provider.health()

    assert health["status"] == "healthy"
    assert health["model"] == "available"
    assert health["version"] == "0.3.14"


@pytest.mark.asyncio
async def test_ollama_provider_health_model_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.3.14"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "other-model:7b"}]},
            )
        return httpx.Response(404)

    provider = _make_provider(handler)
    health = await provider.health()

    assert health["status"] == "unavailable"
    assert health["model"] == "unavailable"
    assert "Configured Ollama model is unavailable" in health["reason"]


@pytest.mark.asyncio
async def test_ollama_provider_health_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Refused")

    provider = _make_provider(handler)
    health = await provider.health()

    assert health["status"] == "unavailable"
    assert "unreachable" in health["reason"]
