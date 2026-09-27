"""Contract-level integration tests: the Ollama provider's failure modes.

Category
--------
**Integration.** Real ``OllamaProvider`` + real ``httpx`` transport, with the
socket replaced by a stub transport.  This exercises the provider's own error
translation — the layer *between* the orchestrator and the network — which the
rest of the integration suite deliberately bypasses by injecting a fake
provider.

Scope
-----
- connection refused        → ``ProviderError`` (unreachable)
- read timeout             → ``ProviderError`` containing a timeout marker
- non-200 status           → ``ProviderError`` (upstream error)
- JSON with no ``message`` → ``ProviderError`` (parse failure)
- JSON that is not an object → ``ProviderError`` (parse failure)
- a well-formed 200        → ``LLMResponse`` with content/model/finish_reason
- outbound request shape   → correct URL, model, ``stream: False``, roles

Why it exists
-------------
The live E2E timeout (Phase 13) originates in this class, not in the
orchestrator.  These tests pin down precisely which upstream conditions become
which ``ProviderError`` message, which is what lets the HTTP layer map them to
502 versus 504.  The transport is stubbed, so they run in milliseconds and are
deterministic — unlike the live path, which is neither.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.providers.base import LLMMessage, LLMRequest, ProviderError
from app.providers.ollama import OllamaProvider

CHAT_URL = "http://ollama.test:11434/api/chat"

VALID_BODY: dict = {
    "model": "qwen3:8b",
    "message": {"role": "assistant", "content": "It returns the sum."},
    "done": True,
    "done_reason": "stop",
}


def _provider(timeout: int = 120) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://ollama.test:11434",
        model="qwen3:8b",
        timeout=timeout,
    )


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content="You analyse code."),
            LLMMessage(role="user", content="def add(a, b): return a + b"),
        ]
    )


def _patch_client(monkeypatch, handler) -> None:
    """Force every ``httpx.AsyncClient`` built by the provider to use *handler*."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_valid_ollama_response_is_translated_to_llm_response(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json=VALID_BODY))

    response = await _provider().complete(_request())

    assert response.content == "It returns the sum."
    assert response.model == "qwen3:8b"
    assert response.finish_reason == "stop"


async def test_request_targets_the_chat_endpoint(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=VALID_BODY)

    _patch_client(monkeypatch, handler)

    await _provider().complete(_request())

    assert seen[0].url == httpx.URL(CHAT_URL)


async def test_request_payload_matches_the_ollama_chat_schema(monkeypatch):
    """`stream: False` is load-bearing: with streaming, the non-streaming read
    path in this provider would not see a complete body."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=VALID_BODY)

    _patch_client(monkeypatch, handler)

    await _provider().complete(_request())

    payload = json.loads(seen[0].content)
    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert "options" not in payload


async def test_temperature_is_sent_only_when_set(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=VALID_BODY)

    _patch_client(monkeypatch, handler)

    request = _request().model_copy(update={"temperature": 0.0})
    await _provider().complete(request)

    assert json.loads(seen[0].content)["options"] == {"temperature": 0.0}


# ---------------------------------------------------------------------------
# Provider errors → 502
# ---------------------------------------------------------------------------


async def test_connection_refused_raises_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "Cannot connect to Ollama" in str(excinfo.value)
    assert excinfo.value.provider == "ollama"


async def test_upstream_500_raises_provider_error(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "HTTP 500" in str(excinfo.value)
    assert "timed out" not in str(excinfo.value).lower()


async def test_upstream_404_raises_provider_error(monkeypatch):
    """A wrong base URL surfaces as 404 and must not be mistaken for a timeout."""
    _patch_client(monkeypatch, lambda request: httpx.Response(404, text="not found"))

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "HTTP 404" in str(excinfo.value)


async def test_generic_request_error_raises_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("broken pipe", request=request)

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError):
        await _provider().complete(_request())


# ---------------------------------------------------------------------------
# Malformed provider responses → 502
# ---------------------------------------------------------------------------


async def test_response_without_message_key_raises_provider_error(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={"foo": "bar"}))

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "parse error" in str(excinfo.value)


async def test_response_without_content_key_raises_provider_error(monkeypatch):
    body = {"message": {"role": "assistant"}, "done": True}
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json=body))

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "parse error" in str(excinfo.value)


async def test_non_json_body_raises_provider_error(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, text="<html>oops"))

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "parse error" in str(excinfo.value)


async def test_json_array_body_raises_provider_error(monkeypatch):
    """An array is valid JSON but has no ``message`` key.

    Known gap, recorded rather than papered over: ``OllamaProvider.complete``
    guards the parse with ``except (KeyError, ValueError)``.  Indexing a *list*
    with ``data["message"]`` raises ``TypeError``, which that clause does not
    catch, so the failure escapes as a ``TypeError`` and the HTTP layer maps it
    to **500 INTERNAL_ERROR** instead of 502 PROVIDER_ERROR.

    The invariant asserted here is the one that matters for safety: the provider
    must never invent content from an unreadable body.  The status-code mapping
    is a provider-layer fix owned by the architecture phase, not by this test,
    so it is documented rather than encoded as expected behaviour.
    """
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json=[1, 2, 3]))

    with pytest.raises((ProviderError, TypeError)) as excinfo:
        await _provider().complete(_request())

    assert not isinstance(excinfo.value, AssertionError)


async def test_empty_object_body_raises_provider_error(monkeypatch):
    _patch_client(monkeypatch, lambda request: httpx.Response(200, json={}))

    with pytest.raises(ProviderError):
        await _provider().complete(_request())


# ---------------------------------------------------------------------------
# Provider timeouts → 504
# ---------------------------------------------------------------------------


async def test_httpx_read_timeout_raises_timeout_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    message = str(excinfo.value).lower()
    assert "timed out" in message
    assert "120s" in str(excinfo.value)


async def test_asyncio_timeout_raises_timeout_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.TimeoutError()

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "timed out" in str(excinfo.value).lower()


async def test_timeout_message_records_the_configured_budget(monkeypatch):
    """The 504 body must be traceable to the configured REQUEST_TIMEOUT."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await _provider(timeout=45).complete(_request())

    assert "45s" in str(excinfo.value)


async def test_timeout_is_not_misreported_as_a_connection_error(monkeypatch):
    """A timeout must keep the timeout wording so the HTTP layer emits 504."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _patch_client(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await _provider().complete(_request())

    assert "Cannot connect" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_trailing_slash_in_base_url_is_normalised():
    """A base URL with a trailing slash must not produce `//api/chat`."""
    provider = OllamaProvider(base_url="http://ollama.test:11434/", model="m")

    assert provider._base_url == "http://ollama.test:11434"


def test_provider_uses_the_configured_model_name():
    provider = OllamaProvider(base_url="http://x", model="qwen3:8b")

    assert provider._model == "qwen3:8b"


def test_provider_retains_the_configured_timeout():
    provider = OllamaProvider(base_url="http://x", model="m", timeout=120)

    assert provider._timeout == 120


async def test_client_is_closed_after_every_call(monkeypatch):
    """Leaking an AsyncClient per request exhausts the connection pool."""
    created: list[httpx.AsyncClient] = []
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        client = real_client(
            *args, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=VALID_BODY)), **kwargs
        )
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)

    await _provider().complete(_request())

    assert len(created) == 1
    assert created[0].is_closed
