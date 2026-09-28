"""Deterministic fake providers used in place of a live LLM.

A live ``qwen3:8b`` completion takes tens of seconds, which is unsuitable for a
normal test run and makes results machine-dependent.  Every provider here
implements the real ``LLMProvider`` interface, so the orchestrator, reasoning
layer, and output-validation pipeline all execute exactly as they do in
production — only the network hop is replaced.

None of these providers open a socket.  ``RecordingProvider`` additionally
captures the ``LLMRequest`` it received so a test can assert on the prompt that
the engine actually built.
"""

from __future__ import annotations

from app.providers.base import LLMProvider, LLMRequest, LLMResponse, ProviderError

from .provider_responses import MALFORMED_BODY, WHITESPACE_TEXT


class StaticProvider(LLMProvider):
    """Return a fixed ``content`` string on every call.

    Parameters
    ----------
    content:
        The text placed in ``LLMResponse.content``.
    model:
        Optional model label echoed back, defaulting to ``"fixture-model"`` so
        a test can assert provider metadata is propagated rather than invented.
    """

    def __init__(self, content: str, model: str = "fixture-model") -> None:
        self._content = content
        self._model = model
        self.call_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the configured content without any network access."""
        self.call_count += 1
        return LLMResponse(content=self._content, model=self._model)


class RecordingProvider(LLMProvider):
    """Return fixed content while recording the prompts it was given.

    Used to verify what the engine sends upstream: system prompt present, source
    code present, requested analyses present, question and context present only
    when supplied.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Record *request* and return the configured content."""
        self.requests.append(request)
        return LLMResponse(content=self._content, model="fixture-model")

    @property
    def call_count(self) -> int:
        """Number of provider calls made so far."""
        return len(self.requests)

    @property
    def last_user_message(self) -> str:
        """Content of the final user-turn message of the most recent call."""
        return self.requests[-1].messages[-1].content


class ProviderErrorProvider(LLMProvider):
    """Raise a non-timeout ``ProviderError`` — maps to HTTP 502."""

    def __init__(self, message: str = "upstream provider returned an error") -> None:
        self._message = message

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Always fail with a generic provider error."""
        raise ProviderError(self._message, provider="fixture")


class ProviderTimeoutProvider(LLMProvider):
    """Raise a timeout ``ProviderError`` — maps to HTTP 504."""

    def __init__(self, seconds: int = 120) -> None:
        self._seconds = seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Always fail with the same wording the Ollama provider uses."""
        raise ProviderError(
            f"Ollama request timed out after {self._seconds}s",
            provider="ollama",
        )


class MalformedProvider(LLMProvider):
    """Return a payload the provider layer cannot read.

    Models an upstream service that answers HTTP 200 with JSON that has no
    ``message.content``.  The failure must surface as ``ProviderError`` (502),
    never as a fabricated summary.
    """

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Simulate an unparseable provider payload."""
        raise ProviderError(
            f"Ollama response parse error: missing key 'content' in {MALFORMED_BODY!r}",
            provider="ollama",
        )


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def static_provider(content: str, model: str = "fixture-model") -> StaticProvider:
    """Return a :class:`StaticProvider` producing *content*."""
    return StaticProvider(content, model=model)


def empty_content_provider() -> StaticProvider:
    """Provider returning an empty string — triggers the fallback summary."""
    return StaticProvider("")


def whitespace_content_provider() -> StaticProvider:
    """Provider returning whitespace only — also triggers the fallback summary."""
    return StaticProvider(WHITESPACE_TEXT)


def provider_error_provider(
    message: str = "upstream provider returned an error",
) -> ProviderErrorProvider:
    """Provider that fails with a non-timeout ``ProviderError``.

    ``message`` is the upstream text.  Pass something secret-looking to assert
    that the HTTP layer keeps it out of the response body.
    """
    return ProviderErrorProvider(message)


def provider_timeout_provider(seconds: int = 120) -> ProviderTimeoutProvider:
    """Provider that fails with a timeout ``ProviderError``."""
    return ProviderTimeoutProvider(seconds=seconds)


def malformed_body_provider() -> MalformedProvider:
    """Provider that returns an unparseable payload."""
    return MalformedProvider()
