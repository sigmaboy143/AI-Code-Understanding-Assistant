"""Provider-independent LLM contracts.

Agent and application code must depend on the types defined here and never on a
concrete provider. Concrete providers (Ollama, OpenAI, Anthropic, ...) implement
:class:`LLMProvider` and translate their own wire format into the neutral types
below, so that swapping a provider never requires changing calling code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "FinishReason",
    "GenerationOptions",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "MessageRole",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "TokenUsage",
]


class MessageRole(str, Enum):
    """Author of a chat message. Providers map these onto their own role names."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class FinishReason(str, Enum):
    """Why generation stopped, normalised across providers."""

    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


class Message(BaseModel):
    """A single chat message.

    Accepts plain dicts (``{"role": "user", "content": "..."}``) as input and
    always validates on construction, so an invalid request fails before any
    provider is called.
    """

    role: MessageRole
    content: str


class GenerationOptions(BaseModel):
    """Provider-neutral generation knobs.

    Every field is optional and defaults to ``None``, which means "let the
    provider apply its own default". A provider that cannot honour a requested
    option may ignore it; it must not raise for a merely unsupported option.
    """

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: tuple[str, ...] | None = None


class TokenUsage(BaseModel):
    """Token accounting for one generation. Fields stay ``None`` when unknown."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMRequest(BaseModel):
    """Input to a single generation: a conversation plus generation settings."""

    messages: list[Message] = Field(min_length=1)
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    model: str | None = None
    """Overrides the provider's default model for this request only."""


class LLMResponse(BaseModel):
    """Normalised result of a single generation."""

    text: str
    model: str
    provider: str
    finish_reason: FinishReason | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    raw: dict[str, Any] | None = None
    """Opaque, provider-specific payload kept for debugging only. Never parse it."""


class ProviderError(Exception):
    """Base class for every failure surfaced through the abstraction.

    Providers must translate their own failures into one of these subclasses so
    callers can react to error *kinds* instead of provider-specific payloads.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.cause = cause


class ProviderConfigurationError(ProviderError):
    """The provider is unusable, e.g. missing credentials or an invalid model."""


class ProviderTimeoutError(ProviderError):
    """The provider did not answer within the allotted time."""


class ProviderRateLimitError(ProviderError):
    """The provider rejected the request because of rate limiting or quota."""


class ProviderResponseError(ProviderError):
    """The provider answered, but the response was unusable."""


class LLMProvider(ABC):
    """Async interface every concrete LLM provider must satisfy.

    Contract:

    * :meth:`generate` is a coroutine and never blocks the event loop.
    * On success it returns a fully populated :class:`LLMResponse`.
    * On failure it raises a :class:`ProviderError` subclass; it never returns
      ``None`` and never leaks a provider-specific exception type.
    * Implementations must not require an external service to be *importable*.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier of the backing provider, e.g. ``"ollama"``."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Default model identifier used when a request does not override it."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Produce a single completion for ``request``."""

    def resolve_model(self, request: LLMRequest) -> str:
        """Return the model a request targets: its override, else the default."""
        return request.model or self.model
