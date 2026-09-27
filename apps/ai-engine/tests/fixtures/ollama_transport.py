"""Deterministic HTTP transports for the *real* ``OllamaProvider``.

Why this module exists
----------------------
``fixtures/failing_providers.py`` supplies providers that raise a pre-baked
``ProviderError``.  That is the correct double for testing the **HTTP layer's
status mapping** — given a provider failure, does the route emit 502 or 504? —
and that is what the existing response-contract tests already do.

Those doubles cannot test the provider's own **error translation**: what a real
upstream condition becomes.  "Ollama is not running", "the model is not pulled",
and "the server returned an HTML error page" are facts about a socket, not about
a Python object.  Reproducing them faithfully requires a real ``OllamaProvider``
performing a real request against a transport that replays a scripted outcome.

This module supplies exactly that missing half, and nothing more:

- a real ``OllamaProvider`` pointed at a reserved-for-testing hostname
- a real ``LLMRequest`` shaped like the ones the orchestrator builds
- an ``httpx.MockTransport`` installer that captures the outbound request

Determinism and safety
----------------------
``.test`` is reserved by RFC 6761 for testing and can never resolve, so a
mistake in the patching can never reach a real host.  No socket is opened, no
model is contacted, and the result is byte-identical on every machine.  Every
upstream body below is hand-written; nothing was captured from a live server.

This is a transport double, not a provider stub.  It does not subclass
``LLMProvider`` and cannot be confused with the fixtures in
``failing_providers.py``.
"""

from __future__ import annotations

import httpx

from app.providers.base import LLMMessage, LLMRequest
from app.providers.ollama import OllamaProvider

#: Reserved-for-testing host (RFC 6761).  Never resolvable, never contacted.
OLLAMA_TEST_BASE_URL = "http://ollama.test:11434"

#: The exact endpoint ``OllamaProvider`` must target.
CHAT_URL = f"{OLLAMA_TEST_BASE_URL}/api/chat"

#: The model tag the tests assert is sent upstream.
FIXTURE_MODEL = "qwen3:8b"


# ---------------------------------------------------------------------------
# Scripted upstream bodies
# ---------------------------------------------------------------------------

VALID_OLLAMA_BODY: dict = {
    "model": FIXTURE_MODEL,
    "message": {"role": "assistant", "content": "It returns the sum."},
    "done": True,
    "done_reason": "stop",
}
"""A well-formed 200 body — the only scripted outcome that must succeed."""

THINKING_OLLAMA_BODY: dict = {
    "model": FIXTURE_MODEL,
    "message": {
        "role": "assistant",
        "thinking": "First I note the function takes two parameters...",
        "content": "It returns the sum.",
    },
    "done": True,
    "done_reason": "stop",
}
"""A 200 body from a *thinking* model: ``qwen3`` splits its output in two.

``message.thinking`` holds the reasoning trace and ``message.content`` holds the
answer.  Hand-written from the shape the live server returns, not captured, so
the fixture stays deterministic and offline.
"""

THINKING_ONLY_OLLAMA_BODY: dict = {
    "model": FIXTURE_MODEL,
    "message": {
        "role": "assistant",
        "thinking": "Still reasoning when the generation budget ran out.",
        "content": "",
    },
    "done": True,
    "done_reason": "length",
}
"""A 200 body where the budget was spent entirely on the reasoning trace.

``content`` is present but empty, which is what a generation cap produces when
the trace does not leave room for an answer.  The provider must return it
unchanged so the existing output-validation fallback owns the outcome.
"""

NULL_THINKING_OLLAMA_BODY: dict = {
    "model": FIXTURE_MODEL,
    "message": {
        "role": "assistant",
        "thinking": None,
        "content": "It returns the sum.",
    },
    "done": True,
    "done_reason": "stop",
}
"""A 200 body carrying an explicit ``"thinking": null``.

Guards against a truthiness bug: reading the trace must never turn a real answer
into an empty one.
"""

NO_MESSAGE_BODY: dict = {"foo": "bar"}
"""HTTP 200 with JSON that has no ``message`` key at all."""

NO_CONTENT_BODY: dict = {"message": {"role": "assistant"}, "done": True}
"""HTTP 200 where ``message`` exists but carries no ``content`` key."""

NON_JSON_BODY = "<html><body>ollama is starting up, retry shortly</body></html>"
"""HTTP 200 whose body is not JSON — a proxy or splash page in front of Ollama."""

MODEL_NOT_FOUND_BODY: dict = {
    "error": "model 'qwen3:8b' not found, try pulling it first"
}
"""Ollama's reply for a tag that exists in config but is not pulled locally.

This is the realistic *model unavailable* case: the engine is configured
correctly and the server is up, but the weights are missing.
"""


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def ollama_provider(timeout: int = 120, model: str = FIXTURE_MODEL) -> OllamaProvider:
    """Return a real ``OllamaProvider`` aimed at the reserved test host."""
    return OllamaProvider(base_url=OLLAMA_TEST_BASE_URL, model=model, timeout=timeout)


def analysis_llm_request() -> LLMRequest:
    """Return a two-turn request shaped like the orchestrator's real prompt.

    Keeps prompt-assembly concerns out of the transport tests, which are about
    what happens *after* the request leaves the engine.
    """
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content="You analyse code."),
            LLMMessage(role="user", content="def add(a, b): return a + b"),
        ]
    )


# ---------------------------------------------------------------------------
# Transport installation
# ---------------------------------------------------------------------------


def install_transport(monkeypatch, handler) -> None:
    """Force every ``httpx.AsyncClient`` the provider builds to use *handler*.

    ``OllamaProvider.complete`` constructs its own ``AsyncClient`` per call, so
    there is nothing to inject.  Patching the constructor is the only seam that
    reaches a real provider without modifying production code.
    """
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def install_upstream(
    monkeypatch,
    *,
    response: httpx.Response | None = None,
    error: Exception | None = None,
) -> list[httpx.Request]:
    """Replay one scripted upstream outcome and return the captured requests.

    Parameters
    ----------
    response:
        The reply to return.  Ignored when *error* is given.
    error:
        The transport-level failure to raise, e.g. ``httpx.ConnectError``.

    Returns
    -------
    list[httpx.Request]
        Every request the provider attempted, in order, so a test can assert
        the URL, model, and payload that were actually sent.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if error is not None:
            raise error
        assert response is not None, "install_upstream needs a response or an error"
        return response

    install_transport(monkeypatch, handler)
    return seen


def connect_error(message: str = "connection refused") -> httpx.ConnectError:
    """Build a ``ConnectError`` bound to :data:`CHAT_URL`.

    ``httpx`` requires the originating request on a transport error, so this
    helper exists purely to supply a well-formed one.
    """
    return httpx.ConnectError(message, request=httpx.Request("POST", CHAT_URL))
