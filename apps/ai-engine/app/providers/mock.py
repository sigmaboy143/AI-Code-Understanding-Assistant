"""Deterministic, offline LLM provider.

Reference implementation of :class:`~app.providers.base.LLMProvider`. It performs
no I/O, needs no credentials and no external service, which makes it usable for
local development and unit tests. It is intentionally not a general-purpose LLM:
it only exercises the abstraction.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.base import (
    FinishReason,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ProviderResponseError,
    TokenUsage,
)

__all__ = ["MockLLMProvider"]

_ECHO_PREFIX = "echo:"


class MockLLMProvider(LLMProvider):
    """Provider that returns canned text, or echoes the prompt when none is set.

    With ``responses=None`` the generated text is the last user message prefixed
    with ``"echo:"``; otherwise the configured responses are returned in order
    and the last one is repeated once exhausted.
    """

    def __init__(
        self,
        *,
        responses: Iterable[str] | None = None,
        provider_name: str = "mock",
        model: str = "mock-echo-1",
    ) -> None:
        self._responses = list(responses) if responses is not None else None
        if self._responses is not None and not self._responses:
            raise ValueError("responses must contain at least one entry")
        self._provider_name = provider_name
        self._model = model
        self._calls = 0

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def call_count(self) -> int:
        """Number of completed :meth:`generate` calls; handy in tests."""
        return self._calls

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self.resolve_model(request)
        if request.messages[-1].role is not MessageRole.USER:
            # The abstraction is chat-shaped, so a trailing non-user message
            # cannot be echoed. Report it as a provider-side response failure.
            raise ProviderResponseError(
                "mock provider can only respond to a request ending in a user message",
                provider=self.provider_name,
                model=model,
            )

        text = self._next_text(request)
        self._calls += 1
        return LLMResponse(
            text=text,
            model=model,
            provider=self.provider_name,
            finish_reason=FinishReason.STOP,
            usage=self._estimate_usage(request, text),
        )

    def _next_text(self, request: LLMRequest) -> str:
        if self._responses is None:
            return f"{_ECHO_PREFIX}{request.messages[-1].content}"
        return self._responses[min(self._calls, len(self._responses) - 1)]

    @staticmethod
    def _estimate_usage(request: LLMRequest, text: str) -> TokenUsage:
        """Rough whitespace-token counts; real providers report their own."""
        prompt_tokens = sum(len(message.content.split()) for message in request.messages)
        completion_tokens = len(text.split())
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
