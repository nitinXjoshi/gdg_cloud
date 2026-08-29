"""Ollama provider: real local LLM via Ollama's HTTP API.

Uses ``httpx`` against ``OLLAMA_BASE_URL`` (default ``http://localhost:11434``).
The configured model must actually exist in the local Ollama installation.

Behavior on failure:
- If Ollama is unreachable or the model is missing, this raises a clear
  ``LLMUnavailableError``. It NEVER falls back to a mock or fabricated response.

Usage:
- Token counts come from Ollama's ``prompt_eval_count`` (input) and
  ``eval_count`` (output) fields when present. When they are absent, usage is
  marked unavailable rather than approximated.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import Settings
from app.services.llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
    UsageInfo,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout_seconds
        self._max_retries = settings.llm_max_retries
        # Injectable for tests (e.g. httpx.MockTransport). Runtime uses None
        # which makes AsyncClient use a real connection pool.
        self._transport = transport

    async def complete(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._base_url}/api/chat"

        # Build messages as system + sanitized prior turns + current user turn.
        # The current user content is always the LAST user message and is never
        # promoted into the system/developer role.
        messages: list[dict[str, str]] = [
            {"role": "system", "content": request.system_prompt},
        ]
        for turn in request.history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": request.user_prompt})

        payload = {
            "model": request.model,
            "stream": False,
            "messages": messages,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }

        timeout = httpx.Timeout(self._timeout)

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                    response = await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("Ollama request timed out") from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise LLMUnavailableError("Ollama is unreachable") from exc

            if response.status_code == 404:
                raise LLMUnavailableError(
                    f"Configured Ollama model is unavailable: {request.model}"
                )
            if response.status_code in (500, 502, 503, 504):
                last_error = LLMError(f"Ollama returned {response.status_code}")
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise last_error
            if response.status_code != 200:
                raise LLMError(f"Ollama returned {response.status_code}: {response.text[:200]}")

            try:
                data = response.json()
            except Exception as exc:
                raise LLMError("Ollama returned an empty or malformed response") from exc
            return self._parse(data, request.model)

        raise LLMError(f"Ollama request failed: {last_error}")

    def _parse(self, data: dict, model: str) -> LLMResponse:
        if not isinstance(data, dict):
            raise LLMError("Ollama returned an empty or malformed response")
        try:
            text = data.get("message", {}).get("content", "")
        except (AttributeError, TypeError):
            text = ""

        if not isinstance(text, str) or not text.strip():
            raise LLMError("Ollama returned an empty or malformed response")

        prompt_eval = data.get("prompt_eval_count")
        eval_count = data.get("eval_count")

        if prompt_eval is not None and eval_count is not None:
            usage = UsageInfo(
                available=True,
                input_tokens=int(prompt_eval),
                output_tokens=int(eval_count),
            )
        else:
            usage = UsageInfo(available=False)

        return LLMResponse(
            text=text,
            model=data.get("model", model),
            usage=usage,
            raw=data,
        )

    async def health(self) -> dict:
        """Real health check: reachability + configured model availability."""
        started = time.perf_counter()
        result: dict = {"provider": self.name, "status": "unavailable"}

        try:
            async with httpx.AsyncClient(timeout=5.0, transport=self._transport) as client:
                version_resp = await client.get(f"{self._base_url}/api/version")
                if version_resp.status_code != 200:
                    result["status"] = "unavailable"
                    result["reason"] = f"version endpoint returned {version_resp.status_code}"
                    return result

                tags_resp = await client.get(f"{self._base_url}/api/tags")
                if tags_resp.status_code != 200:
                    result["status"] = "unavailable"
                    result["reason"] = f"tags endpoint returned {tags_resp.status_code}"
                    return result

                tags_data = tags_resp.json()
                models = [
                    m.get("name")
                    for m in tags_data.get("models", [])
                    if isinstance(m, dict) and m.get("name")
                ]
                model_matched = (
                    self._model in models
                    or f"{self._model}:latest" in models
                    or any(m.startswith(f"{self._model}:") for m in models)
                )
                if not model_matched:
                    result["status"] = "unavailable"
                    result["model"] = "unavailable"
                    result["reason"] = "Configured Ollama model is unavailable"
                    result["available_models"] = models
                    return result

                result["status"] = "healthy"
                result["model"] = "available"
                result["version"] = version_resp.json().get("version")
        except httpx.HTTPError:
            result["status"] = "unavailable"
            result["reason"] = "Ollama is unreachable"

        result["check_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result
