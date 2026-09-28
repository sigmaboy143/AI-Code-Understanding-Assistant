"""Observability and log-safety testing for the AI Engine.

Category
--------
**Integration / observability.**  These tests drive the real ASGI app through
the real routes, providers, and exception handlers, then assert on what the
service actually wrote to the log stream.

What is asserted
----------------
1. **Correlation** — every request carries an identifier, an inbound one is
   honoured, and the identifier on the response matches the one on the log.
2. **Access-log fields** — one line per completed request carrying service,
   method, path, status, duration, and outcome.
3. **Provider timing** — ``provider_call_ms`` is separable from the request's
   own ``duration_ms``, on success and on failure.
4. **Probe quietness** — ``/health`` and ``/ready`` are demoted to ``DEBUG`` so
   a readiness poll cannot bury the lines that matter.
5. **Log safety** — API keys, request bodies, source code, model output, and
   upstream bodies never reach the log.  This makes the guarantee in
   ``README.md`` regression-proof rather than a claim in prose.
6. **A closed outcome vocabulary** — no path can invent a new ``outcome`` value
   without a test noticing, which keeps the documented table honest.

Relationship to the existing tests
---------------------------------
``test_failure_states.py`` already proves each failure state produces the right
status and error code, and ``test_response_contract.py`` already proves the
response *body* contract.  Neither inspects the log.  These tests therefore
assert only what is observable in the log stream, and reuse the same scripted
transport fixtures rather than introducing new doubles.

What is deliberately *not* here
-------------------------------
The live ``qwen3:8b`` timeout is not re-run.  It is a provider/model
generation-behaviour defect diagnosed in Phase 13 and owned by the architecture
phase.  Timeouts are exercised deterministically through the scripted
transport, exactly as ``test_failure_states.py`` does.  No test in this file
claims a live provider success.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import app.config as app_config
from app.config import settings
from app.logging_context import REQUEST_ID_HEADER, correlation_suffix
from app.main import app
from tests.fixtures import (
    CHAT_URL,
    EXPLANATION_TEXT,
    MODEL_NOT_FOUND_BODY,
    connect_error,
    explanation_input,
    install_upstream,
    ollama_provider,
    provider_timeout_provider,
    static_provider,
)

client = TestClient(app)

#: The header the service must echo, re-exported from the module that owns it
#: so this file cannot drift from the implementation's spelling.
HEADER = REQUEST_ID_HEADER

#: Every ``outcome`` value the service is allowed to emit, mirroring the table
#: in ``README.md``.  A new path that logs a value outside this set fails the
#: closed-vocabulary test at the bottom of this file.
DOCUMENTED_OUTCOMES = frozenset(
    {
        "ok",
        "error",
        "validation_error",
        "provider_error",
        "provider_timeout",
        "provider_unavailable",
        "internal_error",
    }
)

#: Canaries planted in every channel sensitive data could leak *from*.  Each is
#: unique to its channel so a leak names the channel that leaked.
CANARY_API_KEY = "CANARY-API-KEY-4f19c2"
CANARY_SOURCE = "CANARY-SOURCE-8ad3e7"
CANARY_CONTEXT = "CANARY-CONTEXT-2b6a91"
CANARY_QUESTION = "CANARY-QUESTION-7c105d"
CANARY_MODEL_OUTPUT = "CANARY-MODEL-OUTPUT-e3d84b"
CANARY_REJECTED = "CANARY-REJECTED-5a72f0"
CANARY_UPSTREAM = "CANARY-UPSTREAM-9f4b13"

ALL_CANARIES = (
    ("api key", CANARY_API_KEY),
    ("source code", CANARY_SOURCE),
    ("supplied context", CANARY_CONTEXT),
    ("question", CANARY_QUESTION),
    ("model output", CANARY_MODEL_OUTPUT),
    ("rejected payload", CANARY_REJECTED),
    ("upstream body", CANARY_UPSTREAM),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(**overrides) -> dict:
    """A valid analysis payload, with optional field overrides applied."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload.update(overrides)
    return payload


def _fields(text: str) -> dict[str, str]:
    """Parse the ``key=value`` pairs out of one rendered log line.

    Splits on whitespace that is *followed by* another ``key=``, so a value
    containing spaces (``detail=Cannot connect to Ollama at http://...``) stays
    attached to its own key instead of being torn into separate tokens.
    """
    parsed: dict[str, str] = {}
    for token in re.split(r"\s+(?=[a-z_]+=)", text):
        key, separator, value = token.partition("=")
        if separator:
            parsed[key] = value
    return parsed


def _engine_lines(caplog) -> list[str]:
    """Every message the AI Engine itself emitted, in order.

    Filters to the ``app`` logger tree so third-party chatter from ``httpx`` or
    ``asyncio`` cannot make a correlation assertion pass or fail by accident.
    """
    return [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("app")
    ]


def _access_lines(caplog) -> list[str]:
    """The ``request completed`` lines, which are the per-request access log."""
    return [line for line in _engine_lines(caplog) if line.startswith("request completed")]


def _only_access_line(caplog) -> dict[str, str]:
    """Assert exactly one access line was written and return its fields."""
    lines = _access_lines(caplog)
    assert len(lines) == 1, f"expected one access line, got {len(lines)}: {lines}"
    return _fields(lines[0])


def _read_timeout() -> httpx.ReadTimeout:
    """A ``ReadTimeout`` bound to a well-formed request, as httpx requires."""
    return httpx.ReadTimeout("timed out", request=httpx.Request("POST", CHAT_URL))


@pytest.fixture(autouse=True)
def _no_live_provider():
    """Fail closed: no test in this file may reach a real provider.

    Without this, a ``POST`` that forgets to patch ``_build_provider`` builds the
    real ``OllamaProvider`` and opens a real connection to the configured host.
    That is slow, non-hermetic, machine-dependent, and — if a daemon happened to
    be running — capable of quietly reporting a *live* provider success.  Tests
    that need a specific provider nest their own patch inside this one.
    """
    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        yield


@pytest.fixture(autouse=True)
def _capture_engine_logs(caplog):
    """Capture the ``app`` logger tree at ``DEBUG`` for every test.

    ``set_level`` is applied to the ``app`` logger rather than relying on the
    service's own ``basicConfig`` level, so these tests do not silently depend
    on the ``LOG_LEVEL`` environment variable.
    """
    caplog.set_level(logging.DEBUG, logger="app")
    caplog.clear()
    yield
    caplog.clear()


@pytest.fixture
def live_api_key(monkeypatch) -> str:
    """Make a canary API key the *effective* configured value.

    ``Settings`` is a frozen dataclass, so the value is swapped by rebuilding the
    instance and repointing both modules that captured it.  Asserting the canary
    took effect is what keeps the leak tests honest: they cannot pass by
    accident because the key was never loaded in the first place.
    """
    replacement = replace(settings, api_key=CANARY_API_KEY)
    monkeypatch.setattr("app.config.settings", replacement)
    monkeypatch.setattr("app.main.settings", replacement)
    assert app_config.settings.api_key == CANARY_API_KEY
    return CANARY_API_KEY


# ---------------------------------------------------------------------------
# 1. Correlation
# ---------------------------------------------------------------------------


def test_a_request_id_is_generated_when_the_caller_sends_none(caplog):
    client.post("/api/v1/code-understanding", json=_payload())
    fields = _only_access_line(caplog)
    request_id = fields["request_id"]
    assert request_id, "an absent inbound id must be replaced by a generated one"
    assert request_id != "-", "the no-request placeholder leaked into a served request"
    assert re.fullmatch(r"[0-9a-f]{32}", request_id), request_id


def test_an_inbound_request_id_is_honoured_verbatim(caplog):
    supplied = "caller-supplied-4a91b7"
    response = client.post(
        "/api/v1/code-understanding",
        json=_payload(),
        headers={HEADER: supplied},
    )
    assert response.headers[HEADER] == supplied
    assert _only_access_line(caplog)["request_id"] == supplied


def test_the_echoed_request_id_identifies_the_log_line(caplog):
    """The header is only useful if the caller can find the lines it names."""
    response = client.post("/api/v1/code-understanding", json=_payload())
    echoed = response.headers[HEADER]
    assert _only_access_line(caplog)["request_id"] == echoed


def test_every_line_for_one_request_shares_the_same_request_id(caplog):
    """A success produces an orchestrator line *and* an access line."""
    client.post("/api/v1/code-understanding", json=_payload())
    request_ids = {
        _fields(line)["request_id"]
        for line in _engine_lines(caplog)
        if "request_id" in line
    }
    assert len(request_ids) == 1, f"request id was not consistent: {request_ids}"


def test_the_request_id_does_not_leak_into_the_next_request(caplog):
    """Context isolation: the second request must not inherit the first's id."""
    first = client.post("/api/v1/code-understanding", json=_payload())
    first_id = first.headers[HEADER]
    caplog.clear()

    second = client.post("/api/v1/code-understanding", json=_payload())
    second_id = second.headers[HEADER]
    assert first_id != second_id
    assert _only_access_line(caplog)["request_id"] == second_id


def test_two_requests_receive_distinct_ids():
    ids = {
        client.post("/api/v1/code-understanding", json=_payload()).headers[HEADER]
        for _ in range(3)
    }
    assert len(ids) == 3


@pytest.mark.parametrize(
    "scenario, expected_status",
    [
        ("success", 200),
        ("provider_unavailable", 503),
        ("provider_error", 502),
        ("provider_timeout", 504),
        ("validation_error", 422),
        ("internal_error", 500),
    ],
)
def test_every_outcome_echoes_the_request_id(
    caplog, monkeypatch, scenario: str, expected_status: int
):
    """The header is the caller's only handle, so it must not be success-only."""
    supplied = f"e2e-{scenario}-id"
    headers = {HEADER: supplied}
    payload = _payload()

    if scenario == "success":
        with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
            response = client.post("/api/v1/code-understanding", json=payload, headers=headers)
    elif scenario == "provider_unavailable":
        with patch("app.main._build_provider", side_effect=RuntimeError("unknown")):
            response = client.post("/api/v1/code-understanding", json=payload, headers=headers)
    elif scenario == "provider_error":
        install_upstream(monkeypatch, error=connect_error())
        with patch("app.main._build_provider", return_value=ollama_provider()):
            response = client.post("/api/v1/code-understanding", json=payload, headers=headers)
    elif scenario == "provider_timeout":
        install_upstream(monkeypatch, error=_read_timeout())
        with patch("app.main._build_provider", return_value=ollama_provider()):
            response = client.post("/api/v1/code-understanding", json=payload, headers=headers)
    elif scenario == "validation_error":
        response = client.post(
            "/api/v1/code-understanding",
            json={"language": "python", "source_code": "   "},
            headers=headers,
        )
    else:  # internal_error
        with patch(
            "app.main.OrchestratorService.analyse", side_effect=RuntimeError("boom")
        ):
            response = client.post("/api/v1/code-understanding", json=payload, headers=headers)

    assert response.status_code == expected_status, response.text
    assert response.headers[HEADER] == supplied
    assert _only_access_line(caplog)["request_id"] == supplied


# ---------------------------------------------------------------------------
# 2. Access-log fields
# ---------------------------------------------------------------------------


def test_the_access_line_reports_the_real_status_and_outcome(caplog):
    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        response = client.post("/api/v1/code-understanding", json=_payload())
    fields = _only_access_line(caplog)
    assert int(fields["status_code"]) == response.status_code == 200
    assert fields["outcome"] == "ok"


def test_the_access_line_reports_a_failure_outcome(caplog):
    response = client.post(
        "/api/v1/code-understanding", json={"language": "python", "source_code": "  "}
    )
    fields = _only_access_line(caplog)
    assert int(fields["status_code"]) == response.status_code == 422
    assert fields["outcome"] == "error"


def test_the_access_line_names_the_service_method_and_endpoint(caplog):
    client.post("/api/v1/code-understanding", json=_payload())
    fields = _only_access_line(caplog)
    assert fields["service"] == "ai-engine"
    assert fields["method"] == "POST"
    assert fields["path"] == "/api/v1/code-understanding"


def test_the_access_line_reports_a_measurable_duration(caplog):
    """Duration is the signal that makes a slow request diagnosable at all."""
    client.post("/api/v1/code-understanding", json=_payload())
    duration = _only_access_line(caplog)["duration_ms"]
    assert re.fullmatch(r"\d+(\.\d+)?", duration), duration
    assert float(duration) >= 0.0


def test_the_outcome_is_in_the_documented_set(caplog):
    client.post("/api/v1/code-understanding", json=_payload())
    assert _only_access_line(caplog)["outcome"] in DOCUMENTED_OUTCOMES


def test_a_rejected_request_is_no_longer_silent(caplog):
    """A 422 previously produced no log line at all — the operator saw nothing."""
    response = client.post(
        "/api/v1/code-understanding", json={"language": "python", "source_code": "  "}
    )
    assert response.status_code == 422
    lines = _engine_lines(caplog)
    assert any("request rejected" in line for line in lines), lines
    assert _only_access_line(caplog)["outcome"] == "error"


# ---------------------------------------------------------------------------
# 3. Provider call timing
# ---------------------------------------------------------------------------


def test_provider_call_duration_is_logged_on_success(caplog):
    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        client.post("/api/v1/code-understanding", json=_payload())
    provider_lines = [line for line in _engine_lines(caplog) if line.startswith("provider call")]
    assert len(provider_lines) == 1, provider_lines
    fields = _fields(provider_lines[0])
    assert fields["outcome"] == "ok"
    assert float(fields["provider_call_ms"]) >= 0.0
    assert fields["model"], "the model actually used must be reported"


def test_provider_call_duration_is_logged_on_failure(caplog, monkeypatch):
    """A slow failure must still be attributable to the provider."""
    install_upstream(monkeypatch, error=connect_error())
    with patch("app.main._build_provider", return_value=ollama_provider()):
        response = client.post("/api/v1/code-understanding", json=_payload())
    assert response.status_code == 502
    provider_lines = [line for line in _engine_lines(caplog) if line.startswith("provider call")]
    assert len(provider_lines) == 1, provider_lines
    fields = _fields(provider_lines[0])
    assert fields["outcome"] == "provider_error"
    assert float(fields["provider_call_ms"]) >= 0.0


def test_request_duration_and_provider_duration_are_separate_signals(caplog, monkeypatch):
    """The whole point: attribute a slow response to the provider, not the engine."""
    install_upstream(monkeypatch, response=httpx.Response(200, json={}))
    with patch("app.main._build_provider", return_value=ollama_provider()):
        client.post("/api/v1/code-understanding", json=_payload())
    engine_lines = _engine_lines(caplog)
    provider = _fields(next(l for l in engine_lines if l.startswith("provider call")))
    access = _only_access_line(caplog)
    assert "provider_call_ms" in provider
    assert "provider_call_ms" not in access, (
        "provider timing belongs on the provider line, not the access line"
    )
    assert "duration_ms" in access and "duration_ms" not in provider


def test_provider_and_access_lines_agree_on_the_request_id(caplog, monkeypatch):
    install_upstream(monkeypatch, error=connect_error())
    with patch("app.main._build_provider", return_value=ollama_provider()):
        client.post("/api/v1/code-understanding", json=_payload())
    ids = {
        _fields(line)["request_id"]
        for line in _engine_lines(caplog)
        if "request_id" in line
    }
    assert len(ids) == 1, f"provider and access lines disagree on the id: {ids}"


# ---------------------------------------------------------------------------
# 4. Probe quietness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_do_not_log_at_info(path: str, caplog):
    """A readiness poll every few seconds must not bury real traffic."""
    response = client.get(path)
    assert response.status_code == 200
    at_or_above_info = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("app") and record.levelno >= logging.INFO
    ]
    assert at_or_above_info == [], f"probe logged at INFO or above: {at_or_above_info}"


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_are_still_visible_at_debug(path: str, caplog):
    response = client.get(path)
    assert response.status_code == 200
    lines = _access_lines(caplog)
    assert len(lines) == 1, lines
    assert _fields(lines[0])["path"] == path


# ---------------------------------------------------------------------------
# 5. Log safety — the regression-proof invariant
# ---------------------------------------------------------------------------


def test_a_successful_request_logs_none_of_its_sensitive_input(
    caplog, live_api_key, monkeypatch
):
    """Canaries in every field a caller controls, plus the model's answer."""
    with patch(
        "app.main._build_provider",
        return_value=static_provider(f"{EXPLANATION_TEXT} {CANARY_MODEL_OUTPUT}"),
    ):
        response = client.post(
            "/api/v1/code-understanding",
            json=_payload(
                source_code=f"def f():\n    # {CANARY_SOURCE}\n    return 1\n",
                context=f"prior context {CANARY_CONTEXT}",
                question=f"explain {CANARY_QUESTION}",
            ),
        )
    assert response.status_code == 200
    _assert_no_canary(caplog)


def test_a_rejected_payload_is_not_echoed_into_the_log(caplog):
    """A rejected body is unvalidated caller input and may contain anything."""
    response = client.post(
        "/api/v1/code-understanding",
        json={"language": "python", "source_code": "  ", "context": CANARY_REJECTED},
    )
    assert response.status_code == 422
    _assert_no_canary(caplog)


def test_a_provider_error_does_not_log_the_upstream_body(caplog, monkeypatch):
    """The provider's status code and base URL are safe; its payload is not."""
    install_upstream(
        monkeypatch,
        response=httpx.Response(
            404, json={**MODEL_NOT_FOUND_BODY, "leaked": CANARY_UPSTREAM}
        ),
    )
    with patch("app.main._build_provider", return_value=ollama_provider()):
        response = client.post("/api/v1/code-understanding", json=_payload())
    assert response.status_code == 502
    _assert_no_canary(caplog)


def test_a_non_json_upstream_body_is_not_logged(caplog, monkeypatch):
    install_upstream(
        monkeypatch,
        response=httpx.Response(200, text=f"<html>{CANARY_UPSTREAM}</html>"),
    )
    with patch("app.main._build_provider", return_value=ollama_provider()):
        response = client.post("/api/v1/code-understanding", json=_payload())
    assert response.status_code == 502
    _assert_no_canary(caplog)


def test_the_api_key_never_reaches_the_log(caplog, live_api_key):
    """The key is live in settings, so a pass cannot come from it never loading."""
    with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
        client.post("/api/v1/code-understanding", json=_payload())
    _assert_no_canary(caplog)


def test_an_empty_model_completion_logs_metadata_not_content(caplog):
    """The validator's fallback path is the easiest place to leak a completion."""
    with patch("app.main._build_provider", return_value=static_provider("")):
        response = client.post("/api/v1/code-understanding", json=_payload())
    assert response.status_code == 200
    assert any(
        r.name.startswith("app.output_validation") for r in caplog.records
    ), "the validator should have warned about empty content"
    _assert_no_canary(caplog)


def _assert_no_canary(caplog) -> None:
    """Fail with the offending channel named if any canary reached the log."""
    log_text = "\n".join(_engine_lines(caplog))
    leaked = [
        name for name, canary in ALL_CANARIES if canary in log_text
    ]
    assert not leaked, f"sensitive value reached the log via: {leaked}\n---\n{log_text}"


# ---------------------------------------------------------------------------
# 6. A closed outcome vocabulary
# ---------------------------------------------------------------------------


def test_no_path_emits_an_undocumented_outcome(monkeypatch):
    """Guards the README table: a new path cannot invent a value unnoticed."""
    stream: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            if record.name.startswith("app"):
                stream.append(record.getMessage())

    collector = _Collector()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(collector)
    root.setLevel(logging.DEBUG)
    try:
        with patch("app.main._build_provider", return_value=static_provider(EXPLANATION_TEXT)):
            client.post("/api/v1/code-understanding", json=_payload())

        # Only one scripted transport can be installed per test: the seam patches
        # the AsyncClient constructor, so a second install would nest inside the
        # first and the first would keep winning.  The timeout therefore uses the
        # existing pre-baked ProviderError double, which is the correct shape for
        # a question about log-field vocabulary rather than about transport.
        install_upstream(monkeypatch, error=connect_error())
        with patch("app.main._build_provider", return_value=ollama_provider()):
            client.post("/api/v1/code-understanding", json=_payload())

        with patch("app.main._build_provider", return_value=provider_timeout_provider()):
            client.post("/api/v1/code-understanding", json=_payload())

        with patch("app.main._build_provider", side_effect=RuntimeError("unknown")):
            client.post("/api/v1/code-understanding", json=_payload())

        client.post(
            "/api/v1/code-understanding", json={"language": "python", "source_code": "  "}
        )

        with patch("app.main.OrchestratorService.analyse", side_effect=RuntimeError("boom")):
            client.post("/api/v1/code-understanding", json=_payload())

        client.get("/health")
        client.get("/ready")
    finally:
        root.removeHandler(collector)
        root.setLevel(previous_level)

    seen = {_fields(line).get("outcome", "") for line in stream}
    seen.discard("")
    assert seen, "no outcomes were observed, so this test proves nothing"
    assert seen <= DOCUMENTED_OUTCOMES, f"undocumented outcome(s): {seen - DOCUMENTED_OUTCOMES}"
    # The paths above must actually have exercised every documented outcome,
    # otherwise the subset assertion above is trivially true.
    assert DOCUMENTED_OUTCOMES <= seen, f"outcomes not exercised: {DOCUMENTED_OUTCOMES - seen}"


# ---------------------------------------------------------------------------
# 7. The correlation helper itself
# ---------------------------------------------------------------------------


def test_the_correlation_suffix_always_names_the_service():
    assert correlation_suffix().strip() == "service=ai-engine request_id=-"


def test_the_correlation_suffix_drops_none_but_keeps_false():
    fields = _fields(correlation_suffix(flag=False, absent=None, present=0))
    assert fields["flag"] == "False"
    assert fields["present"] == "0"
    assert "absent" not in fields


def test_the_correlation_suffix_allows_an_explicit_request_id():
    assert "request_id=explicit" in correlation_suffix(request_id="explicit")
