"""Failure-state testing for the AI Engine's public surface.

Category
--------
**Integration / failure.** Each test provokes a real failure and asserts the
graceful, documented response.  The failure is produced by the *real* provider
performing a *real* request against a scripted transport, or by the real route
handling a real exception — never by a mock of the engine's own error handling.

Failure states covered
----------------------
1. **AI engine unavailable**   — the engine cannot serve; both endpoints must
   agree and must never return a fabricated 200.
2. **Ollama unavailable**      — the daemon is not running → connection failure.
3. **Model unavailable**       — the daemon is up but the tag is not pulled.
4. **Provider timeout**        — the daemon does not answer in time.
5. **Malformed AI response**   — HTTP 200 carrying a body the engine cannot read.
6. **Invalid input**           — the request itself is rejected.
7. **No evidence**             — nothing to ground a claim in.
8. **Insufficient context**    — not enough supplied material to answer.

What is deliberately *not* here
-------------------------------
The live ``qwen3:8b`` timeout is **not** re-run.  It was diagnosed in Phase 13
and its cause was fixed: no generation cap was ever sent upstream, so with
``stream: False`` an uncapped completion could not finish inside the read
timeout and surfaced as a 504.  ``OllamaProvider.complete`` now maps
``LLMRequest.max_tokens`` to ``options.num_predict`` and the reasoning layer
bounds the analysis path, so the live call terminates.  Discarding the
``message.thinking`` trace was never the fault — ``message.content`` is the
answer, and a trace must not be prepended to it.

A live ``qwen3:8b`` run still costs ~1–2 minutes, so it belongs in a manual
integration check rather than here; repeating it would make the suite
unusable.  The timeout is therefore exercised below as a deterministic
transport condition, which is what the mapping actually depends on.

Relationship to the existing failure tests
------------------------------------------
``test_response_contract.py`` already maps a *pre-baked* ``ProviderError`` to
502/503/504, and ``test_provider_error_handling.py`` already checks the
provider's own error *strings*.  Neither checks the composition: a real
upstream condition travelling through a real provider, the real route, and the
real status mapping.  That composition is what this file adds, so it does not
repeat those assertions — it extends them one layer outward.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures import (
    CHAT_URL,
    EXPLANATION_TEXT,
    FABRICATED_REPOSITORY_FACTS,
    FIXTURE_MODEL,
    GIT_FACT_CLAIM_TEXT,
    MODEL_NOT_FOUND_BODY,
    NO_CONTENT_BODY,
    NO_MESSAGE_BODY,
    NON_JSON_BODY,
    RESERVED_EVIDENCE_SOURCE_TYPES,
    VALID_OLLAMA_BODY,
    connect_error,
    dependencies_input,
    explanation_input,
    install_upstream,
    ollama_provider,
    static_provider,
)

client = TestClient(app)

#: The only error codes the engine is allowed to emit.
CONTRACT_ERROR_CODES = frozenset(
    {
        "VALIDATION_ERROR",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_TIMEOUT",
        "PROVIDER_ERROR",
        "INTERNAL_ERROR",
    }
)


def _analysis_payload(**overrides) -> dict:
    """A valid analysis payload, with optional field overrides applied."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload.update(overrides)
    return payload


def _post_with(monkeypatch, **upstream) -> httpx.Response:
    """POST through a real ``OllamaProvider`` against a scripted transport.

    *upstream* is forwarded to :func:`install_upstream`, so a test supplies
    either ``response=`` or ``error=``.  The provider, the route, and the status
    mapping are all real; only the socket is replaced.
    """
    install_upstream(monkeypatch, **upstream)
    with patch("app.main._build_provider", return_value=ollama_provider()):
        return client.post("/api/v1/code-understanding", json=_analysis_payload())


def _post_against_real_ollama(timeout: int = 120) -> httpx.Response:
    """POST through a real ``OllamaProvider`` against an already-installed transport."""
    with patch("app.main._build_provider", return_value=ollama_provider(timeout=timeout)):
        return client.post("/api/v1/code-understanding", json=_analysis_payload())


def _assert_graceful(response: httpx.Response, expected_code: str) -> dict:
    """Assert the standard error envelope and return the decoded body."""
    assert response.status_code >= 400, response.text
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == expected_code
    assert body["error"]["code"] in CONTRACT_ERROR_CODES
    assert body["error"]["message"].strip()
    # The invariant that matters most: a failure never yields an answer.
    assert "summary" not in body
    assert "metadata" not in body
    assert "confidence" not in body
    return body


# ===========================================================================
# 1. AI engine unavailable
# ===========================================================================


def test_unavailable_engine_reports_unavailable_on_the_analysis_path():
    """A provider that cannot be constructed must not yield a 200."""
    with patch("app.main._build_provider", side_effect=RuntimeError("no provider")):
        response = client.post(
            "/api/v1/code-understanding", json=_analysis_payload()
        )

    _assert_graceful(response, "PROVIDER_UNAVAILABLE")
    assert response.status_code == 503


def test_unavailable_engine_reports_unavailable_on_readiness():
    with patch("app.main.settings") as settings:
        settings.is_configured = False
        response = client.get("/ready")

    _assert_graceful(response, "PROVIDER_UNAVAILABLE")
    assert response.status_code == 503


def test_unavailable_engine_signals_identically_on_both_endpoints():
    """NestJS maps one code to one meaning, so both endpoints must agree.

    If readiness said ``PROVIDER_UNAVAILABLE`` while the analysis route said
    something else, a caller could be told the engine is ready and then get an
    error it cannot classify.
    """
    with patch("app.main.settings") as settings:
        settings.is_configured = False
        ready = client.get("/ready")
    with patch("app.main._build_provider", side_effect=RuntimeError("no provider")):
        analysis = client.post(
            "/api/v1/code-understanding", json=_analysis_payload()
        )

    assert ready.json()["error"]["code"] == analysis.json()["error"]["code"]
    assert set(ready.json()["error"]) == set(analysis.json()["error"])


# ===========================================================================
# 2. Ollama unavailable — the daemon is not running
# ===========================================================================


def test_ollama_not_running_maps_to_provider_error(monkeypatch):
    """A refused connection is an upstream failure, not a timeout."""
    install_upstream(monkeypatch, error=connect_error("connection refused"))
    response = _post_against_real_ollama()

    _assert_graceful(response, "PROVIDER_ERROR")
    assert response.status_code == 502


def test_ollama_connection_failure_is_not_reported_as_a_timeout(monkeypatch):
    """Getting the status wrong would send a caller into a pointless retry."""
    install_upstream(monkeypatch, error=connect_error("connection refused"))
    response = _post_against_real_ollama()

    assert response.status_code == 502
    assert response.json()["error"]["code"] != "PROVIDER_TIMEOUT"


def test_ollama_unreachable_does_not_leak_the_upstream_address(monkeypatch):
    """The base URL may be an internal hostname; it must not ship."""
    install_upstream(monkeypatch, error=connect_error("connection refused"))
    response = _post_against_real_ollama()

    assert "ollama.test" not in response.text
    assert "11434" not in response.text


# ===========================================================================
# 3. Model unavailable — the daemon is up but the tag is not pulled
# ===========================================================================


def test_unavailable_model_maps_to_provider_error(monkeypatch):
    """A missing model is an upstream failure, not an engine crash."""
    install_upstream(
        monkeypatch, response=httpx.Response(404, json=MODEL_NOT_FOUND_BODY))
    response = _post_against_real_ollama()

    _assert_graceful(response, "PROVIDER_ERROR")
    assert response.status_code == 502


def test_unavailable_model_message_does_not_quote_the_upstream_error(monkeypatch):
    """The upstream body may name local paths; the caller gets a stable code."""
    install_upstream(monkeypatch, response=httpx.Response(404, json=MODEL_NOT_FOUND_BODY))
    response = _post_against_real_ollama()

    assert "try pulling it first" not in response.text
    assert response.json()["error"]["message"] == (
        "The AI provider returned an error."
    )


def test_missing_model_does_not_invent_an_answer(monkeypatch):
    """No weights, no answer — and certainly no plausible one."""
    install_upstream(monkeypatch, response=httpx.Response(404, json=MODEL_NOT_FOUND_BODY))
    response = _post_against_real_ollama()

    body = response.json()
    assert "summary" not in body
    assert EXPLANATION_TEXT not in response.text


# ===========================================================================
# 4. Provider timeout
# ===========================================================================


def test_provider_timeout_maps_to_gateway_timeout(monkeypatch):
    """A slow daemon is a timeout, which callers retry differently from a 502."""
    install_upstream(monkeypatch, error=httpx.ReadTimeout("timed out", request=httpx.Request("POST", CHAT_URL)),)
    response = _post_against_real_ollama()

    _assert_graceful(response, "PROVIDER_TIMEOUT")
    assert response.status_code == 504


def test_provider_timeout_does_not_disclose_the_configured_budget(monkeypatch):
    """The internal REQUEST_TIMEOUT is an operational detail."""
    install_upstream(monkeypatch, error=httpx.ReadTimeout("timed out", request=httpx.Request("POST", CHAT_URL)),)
    response = _post_against_real_ollama()

    assert "120" not in response.json()["error"]["message"]


def test_pool_exhaustion_also_maps_to_a_timeout(monkeypatch):
    """A connect timeout means the same thing to a caller as a read timeout."""
    install_upstream(monkeypatch, error=httpx.ConnectTimeout(
            "timed out", request=httpx.Request("POST", CHAT_URL)
        ),)
    response = _post_against_real_ollama()

    _assert_graceful(response, "PROVIDER_TIMEOUT")


# ===========================================================================
# 5. Malformed AI response — HTTP 200 with an unreadable body
# ===========================================================================


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=NO_MESSAGE_BODY),
        httpx.Response(200, json=NO_CONTENT_BODY),
        httpx.Response(200, json={}),
        httpx.Response(200, text=NON_JSON_BODY),
    ],
    ids=["no_message_key", "no_content_key", "empty_object", "not_json"],
)
def test_malformed_upstream_body_maps_to_provider_error(monkeypatch, response):
    """An unreadable 200 is a provider error, never a fabricated summary.

    Parametrised over the four body shapes an upstream can realistically
    return.  All four must reach the same conclusion, which is why they are
    one test: the point is the uniformity, not the individual case.
    """
    install_upstream(monkeypatch, response=response)
    actual = _post_against_real_ollama()

    _assert_graceful(actual, "PROVIDER_ERROR")
    assert actual.status_code == 502


def test_malformed_upstream_body_never_leaks_its_content(monkeypatch):
    """An HTML error page must not be reflected back to the caller."""
    install_upstream(monkeypatch, response=httpx.Response(200, text=NON_JSON_BODY))
    response = _post_against_real_ollama()

    assert "starting up" not in response.text
    assert "<html>" not in response.text


def test_a_well_formed_upstream_body_still_succeeds(monkeypatch):
    """Control case: the transport wiring itself must not force a failure.

    Without this, a bug that made every stubbed upstream unreadable would pass
    all the malformed-body tests above.
    """
    install_upstream(monkeypatch, response=httpx.Response(200, json=VALID_OLLAMA_BODY))
    response = _post_against_real_ollama()

    assert response.status_code == 200, response.text
    assert response.json()["summary"] == VALID_OLLAMA_BODY["message"]["content"]


# ===========================================================================
# 6. Invalid input
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        {"language": "python", "source_code": "   "},
        _analysis_payload(question=""),
        _analysis_payload(context=""),
        _analysis_payload(file_path=""),
        _analysis_payload(analyses=None),
    ],
    ids=[
        "blank_source_code",
        "blank_question",
        "blank_context",
        "blank_file_path",
        "null_analyses",
    ],
)
def test_invalid_input_is_rejected_before_any_provider_call(payload):
    """Validation happens first, so a rejected request costs nothing upstream."""
    response = client.post("/api/v1/code-understanding", json=payload)

    _assert_graceful(response, "VALIDATION_ERROR")
    assert response.status_code == 422


def test_invalid_input_never_reaches_the_provider():
    """A rejected request must not consume model capacity."""
    provider = static_provider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        response = client.post(
            "/api/v1/code-understanding",
            json={"language": "python", "source_code": "   "},
        )

    assert response.status_code == 422
    assert provider.call_count == 0


def test_validation_error_does_not_echo_the_submitted_payload():
    """A rejected payload may be large or sensitive; it must not be reflected."""
    secret = "sk-live-ABC123"

    response = client.post(
        "/api/v1/code-understanding",
        json={"language": "python", "source_code": "   ", "context": secret},
    )

    assert response.status_code == 422
    assert secret not in response.text


# ===========================================================================
# 7. No evidence
# ===========================================================================


def test_request_without_a_file_path_still_reports_unknown_confidence():
    """Source code is always submitted, so evidence is never truly empty.

    What the caller loses without a ``file_path`` is attribution, not the
    evidence entry itself.  Confidence must stay UNKNOWN either way.
    """
    payload = explanation_input(file_path=None).model_dump(
        mode="json", exclude_none=True
    )

    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 200, response.text
    confidence = response.json()["confidence"]
    assert confidence["level"] == "UNKNOWN"
    assert confidence["evidence"]
    assert confidence["evidence"][0]["file_path"] is None
    assert confidence["notes"].strip()


def test_a_bare_snippet_never_reports_confirmed():
    """The smallest possible request must not look better than a rich one."""
    payload = {
        "source_code": "def add(a, b):\n    return a + b\n",
        "language": "python",
    }

    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["confidence"]["level"] == "UNKNOWN"


# ===========================================================================
# 8. Insufficient context
# ===========================================================================


def test_insufficient_context_fabricates_nothing_structural():
    """A confident answer about absent history must stay unstructural."""
    payload = dependencies_input().model_dump(mode="json", exclude_none=True)

    with patch(
        "app.main._build_provider", return_value=static_provider(GIT_FACT_CLAIM_TEXT)
    ):
        response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure"] is None
    assert body["improvements"] == []
    assert body["dependencies"]["impacts"] == []


def test_insufficient_context_never_invents_git_or_test_evidence():
    """Reserved evidence types stay reserved however confident the prose is."""
    with patch(
        "app.main._build_provider", return_value=static_provider(GIT_FACT_CLAIM_TEXT)
    ):
        response = client.post(
            "/api/v1/code-understanding", json=_analysis_payload()
        )

    body = response.json()
    emitted = {item["source_type"] for item in body["confidence"]["evidence"]}
    assert not emitted & set(RESERVED_EVIDENCE_SOURCE_TYPES)

    rendered = " ".join(
        f"{item['description'] or ''} {item['file_path'] or ''}"
        for item in body["confidence"]["evidence"]
    )
    for fact in FABRICATED_REPOSITORY_FACTS:
        assert fact not in rendered


def test_insufficient_context_does_not_upgrade_confidence():
    """More prose is not more evidence."""
    with patch(
        "app.main._build_provider", return_value=static_provider(GIT_FACT_CLAIM_TEXT)
    ):
        response = client.post(
            "/api/v1/code-understanding", json=_analysis_payload()
        )

    body = response.json()
    assert body["confidence"]["level"] == "UNKNOWN"
    assert body["confidence"]["notes"].strip()


def test_unparseable_context_is_ignored_rather_than_guessed():
    """Broken supplementary material must not yield speculative structure."""
    payload = dependencies_input(
        source_code="def add(a, b):\n    return a + b\n",
        context="this is not valid python ((( ",
    ).model_dump(mode="json")

    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["dependencies"]["dependencies"] == []


def test_confidence_is_never_invented_when_the_answer_is_empty():
    """A blank completion yields a fallback, still honestly labelled."""
    with patch("app.main._build_provider", return_value=static_provider("")):
        response = client.post(
            "/api/v1/code-understanding", json=_analysis_payload()
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"].strip()
    assert body["confidence"]["level"] == "UNKNOWN"


# ===========================================================================
# Cross-cutting: one envelope for every failure
# ===========================================================================


def test_the_model_tag_sent_upstream_is_the_configured_one(monkeypatch):
    """A failure-state harness must not quietly change what the engine asks for.

    Guards the fixture wiring itself: if the tests were aimed at the wrong
    model, every "unavailable model" case would be passing for the wrong
    reason.
    """
    seen = install_upstream(
        monkeypatch, response=httpx.Response(200, json=VALID_OLLAMA_BODY)
    )
    _post_against_real_ollama()

    assert seen[0].url == httpx.URL(CHAT_URL)
    assert FIXTURE_MODEL in seen[0].content.decode()

