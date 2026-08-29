"""LLM provider abstraction.

The application talks to ``LLMProvider`` rather than a vendor SDK, isolating
provider-specific request/response formatting. The only runtime implementation is
``OllamaProvider`` (a real local model). Tests may substitute their own
``LLMProvider`` or mock the underlying HTTP transport; the runtime path never
falls back to fabricated data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMRequest:
    """A normalized, provider-agnostic LLM request."""

    system_prompt: str
    user_prompt: str
    model: str
    max_output_tokens: int
    temperature: float = 0.0
    history: list[dict[str, str]] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class UsageInfo:
    """Token usage as reported by the provider.

    When the provider does not return exact token counts, ``available`` is
    ``False`` and the numeric fields are ``None``. Callers must never substitute
    an estimate for those missing values.
    """

    available: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    """A normalized LLM response with genuine usage metadata."""

    text: str
    model: str = ""
    usage: UsageInfo | None = None
    raw: dict | None = None


class LLMError(Exception):
    """Raised for any provider-level failure (network, auth, timeout, etc.)."""


class LLMTimeoutError(LLMError):
    """Raised when a provider call exceeds its configured timeout."""


class LLMUnavailableError(LLMError):
    """Raised when the provider or configured model is unreachable/unavailable."""


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    name: str = "base"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a completion for the given normalized request."""
        raise NotImplementedError

    async def health(self) -> dict:
        """Report provider health. Providers should override for real checks."""
        return {"provider": self.name, "status": "unknown"}
