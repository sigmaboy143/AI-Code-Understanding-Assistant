"""Focused unit tests for the ``think`` flag ``OllamaProvider`` sends upstream.

Category
--------
**Unit.**  A real ``OllamaProvider`` with the socket replaced by
``httpx.MockTransport``.  No server, no model, no network.

Why this module exists
----------------------
Bounding generation (``options.num_predict``) was not sufficient on its own.
``qwen3`` is a reasoning model, and the tokens of its ``thinking`` trace come out
of the *same* budget as the answer.  With the cap applied but thinking left on,
the cap is largely spent on the trace: measured live, the full five-analysis
prompt still exceeded the 120-second read budget and surfaced as a 504.

The fix sends ``"think": False`` for ``qwen3`` tags.  This module pins exactly
that decision and its blast radius, so the flag cannot be dropped by accident and
cannot leak onto models it was never measured against.

Scope
-----
- ``qwen3`` tags            → ``"think": False`` is sent
- the cap still travels     → ``options.num_predict`` is unaffected by the flag
- non-``qwen3`` tags        → **no** ``think`` key at all (not ``True``, absent)
- ``temperature=0.0``       → still does not drop ``num_predict``
- error mapping             → unchanged when the flag is being sent
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.providers.base import LLMRequest, ProviderError
from app.reasoning import DEFAULT_MAX_TOKENS, build_reasoning_request
from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest
from tests.fixtures import (
    VALID_OLLAMA_BODY,
    analysis_llm_request,
    connect_error,
    install_transport,
    ollama_provider,
)

#: Tags that must receive ``"think": False``.  The bare tag, a sized tag, a
#: quantised tag, and the explicit thinking variant all start with ``qwen3``.
QWEN3_TAGS = ["qwen3", "qwen3:8b", "qwen3:4b-instruct", "qwen3:32b-q4_K_M"]

#: Tags that must **not** receive the flag.  Two reasons to keep each: they are
#: not reasoning models, or they are reasoning models this was never measured
#: against.  Either way the provider adds nothing it did not add before.
NON_QWEN3_TAGS = [
    "llama3",
    "llama3:8b",
    "codellama",
    "qwen2.5:7b",
    "qwen2.5-coder:7b",
    "deepseek-r1:8b",
    "mistral",
    "gemma3:4b",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with(**updates) -> LLMRequest:
    """The shared two-turn fixture request, with generation params applied."""
    return analysis_llm_request().model_copy(update=updates)


async def _payload_sent(monkeypatch, request: LLMRequest, model: str) -> dict:
    """Complete *request* as *model* against a scripted 200; return the JSON sent."""
    seen: list[httpx.Request] = []

    def handler(raw: httpx.Request) -> httpx.Response:
        seen.append(raw)
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    await ollama_provider(model=model).complete(request)
    assert len(seen) == 1, "expected exactly one upstream attempt"
    return json.loads(seen[0].content)


# ===========================================================================
# qwen3 receives think=false
# ===========================================================================


@pytest.mark.parametrize("model", QWEN3_TAGS)
async def test_a_qwen3_tag_is_told_not_to_think(monkeypatch, model):
    """The reason the flag exists: the trace shares the generation budget.

    Every ``qwen3`` spelling is covered, not just the tag this happens to run
    with, because the check is on the tag prefix and a new quantisation must not
    silently lose the flag.
    """
    payload = await _payload_sent(monkeypatch, _with(), model)

    assert payload["think"] is False


async def test_think_is_false_and_not_true_or_a_string(monkeypatch):
    """The flag is a JSON boolean, so a truthy string would not disable thinking.

    Ollama type-checks this field.  ``"false"`` or ``"False"`` would be rejected
    or ignored, leaving the original unbounded-trace behaviour in place while the
    test suite still passed on a truthiness check.
    """
    payload = await _payload_sent(monkeypatch, _with(), "qwen3:8b")

    assert payload["think"] is False
    assert isinstance(payload["think"], bool)


# ===========================================================================
# The cap still travels alongside the flag
# ===========================================================================


async def test_the_generation_cap_is_still_sent_for_qwen3(monkeypatch):
    """Adding ``think`` must not cost the request its ``num_predict`` bound.

    These are two different protections — the cap stops an over-long generation,
    the flag stops the budget being spent on reasoning.  A change that fixed the
    second by dropping the first would look like a fix and behave like the
    original bug.
    """
    payload = await _payload_sent(monkeypatch, _with(max_tokens=512), "qwen3:8b")

    assert payload["options"]["num_predict"] == 512
    assert payload["think"] is False


async def test_the_real_analysis_path_sends_both_the_cap_and_the_flag(monkeypatch):
    """The end-to-end shape that matters: orchestrator request, ``qwen3`` model.

    Asserted on the request ``build_reasoning_request`` really produces rather
    than a hand-built one, so the test fails if either the default cap or the
    flag stops reaching the wire on the real path.
    """
    request = CodeUnderstandingRequest(
        source_code="def add(a, b):\n    return a + b\n",
        language="python",
        analyses=[AnalysisType.EXPLANATION],
    )
    llm_request = build_reasoning_request(request)

    assert llm_request.max_tokens == DEFAULT_MAX_TOKENS

    payload = await _payload_sent(monkeypatch, llm_request, "qwen3:8b")

    assert payload["options"] == {"num_predict": DEFAULT_MAX_TOKENS}
    assert payload["think"] is False


async def test_a_zero_temperature_still_reaches_num_predict(monkeypatch):
    """``temperature=0.0`` is falsy — neither knob may key off truthiness.

    Regression guard for the interaction of the two flags on one payload: a
    falsy-check bug in either mapping would silently drop the generation cap.
    """
    payload = await _payload_sent(
        monkeypatch, _with(temperature=0.0, max_tokens=1), "qwen3:8b"
    )

    assert payload["options"]["num_predict"] == 1
    assert payload["think"] is False


async def test_temperature_and_num_predict_survive_next_to_the_flag(monkeypatch):
    """All three values coexist in one payload without clobbering each other."""
    payload = await _payload_sent(
        monkeypatch, _with(temperature=0.7, max_tokens=256), "qwen3:8b"
    )

    assert payload["options"] == {"temperature": 0.7, "num_predict": 256}
    assert payload["think"] is False


# ===========================================================================
# Non-qwen3 models are untouched
# ===========================================================================


@pytest.mark.parametrize("model", NON_QWEN3_TAGS)
async def test_a_non_qwen3_model_is_never_told_anything_about_thinking(
    monkeypatch, model
):
    """No ``think`` key at all — not ``True``, not ``False``, absent.

    Sending ``think`` to a model that does not support the field could be
    rejected by the server, and sending ``True`` would change behaviour on a
    model this was never measured against.  Absence is the only safe value, so
    the key is checked for absence rather than for a value.

    ``qwen2.5`` is here deliberately: it shares a prefix with ``qwen3`` and must
    not be caught by a sloppy ``"qwen" in model`` test.
    """
    payload = await _payload_sent(monkeypatch, _with(), model)

    assert "think" not in payload


async def test_a_non_qwen3_model_keeps_its_generation_cap(monkeypatch):
    """The cap is model-independent; only the flag is ``qwen3``-scoped."""
    payload = await _payload_sent(monkeypatch, _with(max_tokens=128), "llama3")

    assert payload["options"]["num_predict"] == 128
    assert "think" not in payload


# ===========================================================================
# Everything the payload already carried is preserved
# ===========================================================================


async def test_the_pre_existing_payload_keys_are_unchanged(monkeypatch):
    """``model``, ``messages`` and ``stream`` survive; ``think`` is purely additive.

    ``stream: False`` is what makes the call a single blocking read, so dropping
    or flipping it would change the failure mode the whole cap was added for.
    """
    payload = await _payload_sent(monkeypatch, _with(max_tokens=64), "qwen3:8b")

    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert set(payload) == {"model", "messages", "stream", "options", "think"}


# ===========================================================================
# Error mapping is unchanged while the flag is in play
# ===========================================================================


async def test_a_connection_failure_still_maps_to_provider_error(monkeypatch):
    """The flag must not change how a dead upstream is reported."""

    def handler(raw: httpx.Request) -> httpx.Response:
        raise connect_error()

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider(model="qwen3:8b").complete(_with(max_tokens=64))

    assert "Cannot connect to Ollama" in str(excinfo.value)


async def test_a_non_200_still_maps_to_provider_error(monkeypatch):
    """An upstream HTTP error is still a provider error, not a flag problem."""
    install_transport(monkeypatch, lambda raw: httpx.Response(500, text="boom"))

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider(model="qwen3:8b").complete(_with(max_tokens=64))

    assert "HTTP 500" in str(excinfo.value)


async def test_a_timeout_still_maps_to_the_timeout_wording(monkeypatch):
    """Timeouts keep their own wording, so callers can still tell them apart.

    The distinction matters: a timeout surfaces as 504 and a connection failure as
    502, and the flag must not blur that.
    """

    def handler(raw: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=raw)

    install_transport(monkeypatch, handler)

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider(model="qwen3:8b").complete(_with(max_tokens=64))

    assert "timed out" in str(excinfo.value)


async def test_a_missing_model_still_maps_to_provider_error(monkeypatch):
    """The realistic "weights not pulled" body is still an ordinary provider error."""
    install_transport(monkeypatch, lambda raw: httpx.Response(404, text="not found"))

    with pytest.raises(ProviderError) as excinfo:
        await ollama_provider(model="qwen3:8b").complete(_with(max_tokens=64))

    assert "HTTP 404" in str(excinfo.value)


# ===========================================================================
# The flag is not reachable through the public contract
# ===========================================================================


def test_the_llm_contract_gained_no_think_field():
    """``think`` is decided by the provider from the model tag, not by callers.

    The public ``LLMRequest`` is unchanged, so no caller can set, override, or
    depend on the flag.  That keeps the decision in one place and means existing
    callers behave identically.
    """
    fields = set(LLMRequest.model_fields)

    assert "think" not in fields
    assert "num_predict" not in fields
    assert {"messages", "temperature", "max_tokens"} <= fields
