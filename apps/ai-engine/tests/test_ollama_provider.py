"""Focused unit tests for ``OllamaProvider``: request translation and response handling.

Category
--------
**Unit.**  A real ``OllamaProvider`` with the socket replaced by
``httpx.MockTransport``.  No server, no model, no network — every assertion runs
in milliseconds and is identical on every machine.

Why this module exists
----------------------
Phase 13 traced the live ``qwen3:8b`` 504 to a single provider-layer omission:
``LLMRequest.max_tokens`` was never sent upstream, so ``/api/chat`` was asked for
an *unbounded* completion while ``stream: False`` requires the whole generation
to finish before a response body exists.  Measured against the live server, the
real analysis prompt emits ~941 tokens (a ``thinking`` trace plus the answer) at
roughly 9 tokens/second — about 100 seconds, past the 120-second read budget in
the worst observed run.

``tests/integration/test_provider_error_handling.py`` already pins the error
strings.  This module pins the two things that were missing: the *outbound*
translation of ``max_tokens``, and the handling of a thinking model's split
``thinking``/``content`` message.

Scope
-----
- ``max_tokens``      → ``options.num_predict`` (and nothing else invented)
- ``temperature``     → ``options.temperature`` (unchanged)
- ``options``         → omitted entirely when neither is set (unchanged)
- ``message.thinking``→ discarded; ``message.content`` is the answer
- empty ``content``   → returned as-is for the validator to own (unchanged)
- error mapping       → connect / non-200 / parse → ``ProviderError`` (regression)
- timeout mapping     → ``httpx`` and ``asyncio`` timeouts → timeout wording
- malformed bodies    → no message / no content / non-JSON / non-object
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.providers.base import LLMRequest, ProviderError
from app.providers.ollama import OllamaProvider
from app.reasoning import DEFAULT_MAX_TOKENS, build_reasoning_request
from app.schemas.code_understanding import (
    AnalysisType,
    CodeUnderstandingRequest,
)
from tests.fixtures import (
    FIXTURE_MODEL,
    NO_CONTENT_BODY,
    NO_MESSAGE_BODY,
    NON_JSON_BODY,
    NULL_THINKING_OLLAMA_BODY,
    THINKING_ONLY_OLLAMA_BODY,
    THINKING_OLLAMA_BODY,
    VALID_OLLAMA_BODY,
    analysis_llm_request,
    install_transport,
    ollama_provider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with(**updates) -> LLMRequest:
    """The shared two-turn fixture request, with generation params applied."""
    return analysis_llm_request().model_copy(update=updates)


async def _payload_sent(monkeypatch, request: LLMRequest) -> dict:
    """Complete *request* against a scripted 200 and return the JSON sent."""
    seen: list[httpx.Request] = []

    def handler(raw: httpx.Request) -> httpx.Response:
        seen.append(raw)
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    await ollama_provider().complete(request)
    return json.loads(seen[0].content)


# ===========================================================================
# max_tokens → options.num_predict  (the Phase 13 fix)
# ===========================================================================


async def test_max_tokens_is_sent_as_num_predict(monkeypatch):
    """Ollama spells "max tokens" ``options.num_predict``.

    Without this the upstream is asked for an unbounded completion, which is the
    defect that made the live request time out.
    """
    payload = await _payload_sent(monkeypatch, _with(max_tokens=768))

    assert payload["options"] == {"num_predict": 768}


async def test_num_predict_is_omitted_when_max_tokens_is_unset(monkeypatch):
    """No cap requested means no cap sent — the provider adds nothing of its own."""
    payload = await _payload_sent(monkeypatch, _with())

    assert "options" not in payload


async def test_temperature_and_num_predict_are_sent_together(monkeypatch):
    """Both knobs share one ``options`` object; neither may clobber the other."""
    payload = await _payload_sent(
        monkeypatch, _with(temperature=0.2, max_tokens=256)
    )

    assert payload["options"] == {"temperature": 0.2, "num_predict": 256}


async def test_a_zero_temperature_still_reaches_num_predict(monkeypatch):
    """``temperature=0.0`` is falsy — the mapping must not key off truthiness.

    A falsy-check bug here would silently drop the generation cap, which is
    exactly the bug being fixed.
    """
    payload = await _payload_sent(monkeypatch, _with(temperature=0.0, max_tokens=1))

    assert payload["options"]["num_predict"] == 1


async def test_the_real_analysis_path_sends_a_generation_cap(monkeypatch):
    """``build_reasoning_request`` must bound generation, not rely on a caller.

    The orchestrator builds the request with no generation parameters, so
    without a default the cap would never reach the provider and the live
    timeout would return.
    """
    request = CodeUnderstandingRequest(
        source_code="def add(a, b):\n    return a + b\n",
        language="python",
        analyses=[AnalysisType.EXPLANATION],
    )
    llm_request = build_reasoning_request(request)

    assert llm_request.max_tokens == DEFAULT_MAX_TOKENS

    payload = await _payload_sent(monkeypatch, llm_request)

    assert payload["options"] == {"num_predict": DEFAULT_MAX_TOKENS}


def test_default_max_tokens_is_a_positive_bound():
    """A cap of zero or None would reintroduce the unbounded call."""
    assert isinstance(DEFAULT_MAX_TOKENS, int)
    assert DEFAULT_MAX_TOKENS >= 1


# ===========================================================================
# Thinking models — message.thinking vs message.content
# ===========================================================================


async def test_thinking_trace_is_discarded_and_content_is_returned(monkeypatch):
    """``qwen3`` splits its reply: the trace is not the answer.

    ``LLMResponse`` has one field for text, so the answer is ``message.content``.
    The trace must not be prepended to it or leak into the summary.
    """
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=THINKING_OLLAMA_BODY),
    )

    response = await ollama_provider().complete(analysis_llm_request())

    assert response.content == "It returns the sum."
    assert "First I note" not in response.content


async def test_null_thinking_field_does_not_destroy_the_answer(monkeypatch):
    """A non-thinking model may send ``"thinking": null`` explicitly.

    Reading the trace through a truthiness check would blank a real answer.
    """
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=NULL_THINKING_OLLAMA_BODY),
    )

    response = await ollama_provider().complete(analysis_llm_request())

    assert response.content == "It returns the sum."


async def test_a_budget_spent_on_thinking_yields_empty_content_not_an_error(
    monkeypatch,
):
    """When the cap leaves no room for an answer, the provider must not invent one.

    Returning the empty string is deliberate: output validation already owns that
    case and substitutes its documented fallback.  Raising here would turn a
    capped generation into a 502, which is a different failure.
    """
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=THINKING_ONLY_OLLAMA_BODY),
    )

    response = await ollama_provider().complete(analysis_llm_request())

    assert response.content == ""
    assert response.finish_reason == "length"


async def test_thinking_only_message_without_content_is_a_parse_error(monkeypatch):
    """A missing ``content`` key stays malformed regardless of the trace.

    Reading the trace as a substitute would fabricate an answer out of a
    reasoning fragment.
    """
    body = {
        "message": {"role": "assistant", "thinking": "I was still reasoning."},
        "done": True,
    }
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=body))

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider().complete(analysis_llm_request())

    assert "parse error" in str(excinfo.value)


# ===========================================================================
# Regression — provider error mapping (unchanged by this fix)
# ===========================================================================


async def test_connection_refused_maps_to_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider().complete(analysis_llm_request())

    assert "Cannot connect to Ollama" in str(excinfo.value)
    assert excinfo.value.provider == "ollama"


@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_non_200_status_maps_to_provider_error(monkeypatch, status):
    """An upstream error is a provider error, never a fabricated answer."""
    install_transport(
        monkeypatch, lambda request: httpx.Response(status, text="upstream boom")
    )

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider().complete(analysis_llm_request())

    message = str(excinfo.value)
    assert f"HTTP {status}" in message
    # Must not be mistaken for a timeout, which the route maps to 504.
    assert "timed out" not in message.lower()


async def test_generic_transport_error_maps_to_provider_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("broken pipe", request=request)

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError):
        await ollama_provider().complete(analysis_llm_request())


# ===========================================================================
# Regression — timeout mapping (unchanged by this fix)
# ===========================================================================


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectTimeout("timed out"),
        httpx.WriteTimeout("timed out"),
        asyncio.TimeoutError(),
    ],
    ids=["read", "connect", "write", "asyncio"],
)
async def test_every_timeout_maps_to_the_timeout_wording(monkeypatch, error):
    """The 502/504 split is decided by wording, so all four must keep it."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider(timeout=97).complete(analysis_llm_request())

    assert "timed out" in str(excinfo.value).lower()
    assert "97s" in str(excinfo.value)


async def test_a_timeout_is_never_reported_as_a_connection_error(monkeypatch):
    """Getting this wrong sends a caller into a pointless retry."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider().complete(analysis_llm_request())

    assert "Cannot connect" not in str(excinfo.value)


# ===========================================================================
# Regression — malformed response handling (unchanged by this fix)
# ===========================================================================


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=NO_MESSAGE_BODY),
        httpx.Response(200, json=NO_CONTENT_BODY),
        httpx.Response(200, json={}),
        # ``text=`` on purpose: ``json=<str>`` would emit a *valid* JSON string
        # and stop testing the unparseable-body path.
        httpx.Response(200, text=NON_JSON_BODY),
    ],
    ids=["no_message", "no_content", "empty_object", "not_json"],
)
async def test_unreadable_bodies_map_to_a_parse_error(monkeypatch, response):
    """The provider must never invent content from a body it cannot read."""
    install_transport(monkeypatch, lambda request: response)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider().complete(analysis_llm_request())

    assert "parse error" in str(excinfo.value)


async def test_a_well_formed_body_still_succeeds_after_the_fix(monkeypatch):
    """Control case: the cap must not break the ordinary non-thinking path."""
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )

    response = await ollama_provider().complete(_with(max_tokens=256))

    assert response.content == VALID_OLLAMA_BODY["message"]["content"]
    assert response.model == FIXTURE_MODEL
    assert response.finish_reason == "stop"


# ===========================================================================
# Regression — construction is untouched
# ===========================================================================


def test_base_url_trailing_slash_is_normalised():
    assert OllamaProvider(base_url="http://x:11434/")._base_url == "http://x:11434"


def test_model_and_timeout_are_retained():
    provider = OllamaProvider(base_url="http://x", model=FIXTURE_MODEL, timeout=120)

    assert provider._model == FIXTURE_MODEL
    assert provider._timeout == 120
