"""AI-side logging and observability contract.

Category
--------
**Integration.**  Real FastAPI application through ``TestClient``; only the LLM
provider is replaced, and where the real provider matters the socket is replaced
by a scripted transport.

Scope
-----
Two things are asserted here, and nothing else.

**Logging (Phase 33)** — the service emits the operational facts an operator
needs (correlation ID, service, operation, duration, outcome, error
classification) and emits **no** credential, prompt, or submitted source code.

**Observability (Phase 34)** — the AI side can tell these apart using real
behaviour rather than a claim: AI-engine failure, provider failure, provider
timeout, provider unavailability, request duration, provider-call duration, and
the liveness/readiness split.

Why it exists
-------------
``test_health_contract.py`` proves ``/health`` and ``/ready`` return the right
status codes and ``test_failure_states.py`` proves the right codes reach the
caller.  Neither says anything about what an operator can *see*: before this
file the service had no correlation ID, no durations, and no success-path log
line at all, so a slow request and a failed one were indistinguishable outside
the HTTP response.

What is deliberately *not* here
-------------------------------
- The live ``qwen3:8b`` timeout (Phase 13) is not re-run.  Provider-call timing
  is asserted against a scripted transport, so the suite stays fast and
  deterministic.
- Member 1's logging and observability contract is not touched or mirrored.  No
  log format, level, or field used by the NestJS side is assumed here.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.observability import REQUEST_ID_HEADER, SERVICE_NAME
from tests.fixtures import (
    CHAT_URL,
    EXPLANATION_TEXT,
    connect_error,
    explanation_input,
    install_upstream,
    ollama_provider,
    provider_error_provider,
    provider_timeout_provider,
    static_provider,
)

client = TestClient(app)

#: Logger that emits the one access-log line per request.
ACCESS_LOGGER = "app.observability"

#: Logger that emits the provider-call timing line.
PROVIDER_LOGGER = "app.orchestrator.service"

#: Root of the logger tree this service configures.
ENGINE_LOGGER = "app"

#: ``LogRecord`` attributes the :mod:`logging` module sets itself.  Anything a
#: record carries beyond this set was added by this service — as a correlation
#: field or as an ``extra=`` payload — and is flattened into the text scanned by
#: the confidentiality tests.  That is what makes those tests able to catch a
#: secret hidden in a structured field rather than only in a message.
_BUILTIN_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

#: A string that must never appear in a log record, in any field.
SECRET_API_KEY = "sk-live-OBSERVABILITY-TRIPWIRE-9f3a"

#: A string planted in the submitted source code.
SECRET_SOURCE_LINE = "TRIPWIRE_SOURCE_LINE_a41c"

#: A string planted in the supplementary context.
SECRET_CONTEXT_LINE = "TRIPWIRE_CONTEXT_LINE_b27e"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _capture_info_records(caplog):
    """Capture INFO records too.

    The engine's own logger tree is configured at INFO, but pytest's ``caplog``
    only captures WARNING and above by default, so without this every
    access-log assertion below would silently pass on an empty list.
    """
    caplog.set_level(logging.INFO)


def _rendered(records) -> str:
    """Flatten every record's message *and* custom attributes into one string.

    Reading only ``getMessage()`` would miss a secret smuggled through
    ``extra=``; reading only the attributes would miss one in the message text.
    """
    parts = []
    for record in records:
        parts.append(f"{record.name} {record.levelname} {record.getMessage()}")
        for key, value in vars(record).items():
            if key in _BUILTIN_RECORD_FIELDS:
                continue
            parts.append(f"{key}={value}")
    return "\n".join(parts)


def _engine_records(records) -> list:
    """Return only the records produced by this service's own logger tree.

    ``caplog`` also captures third-party loggers, and ``httpx`` logs the full
    request URL at INFO — so a blanket scan of every captured record would trip
    over a library's line rather than over the engine's.  Which third-party
    loggers are enabled is a deployment decision, not something this service
    configures: only the ``app`` tree is given a handler and a level here, and
    every other logger stays at the :mod:`logging` default of ``WARNING``, so
    ``httpx``'s URL line is not emitted by the engine as shipped.
    """
    return [
        record
        for record in records
        if record.name == ENGINE_LOGGER
        or record.name.startswith(f"{ENGINE_LOGGER}.")
    ]


def _with(record, attribute, default=None):
    """Return *attribute* from *record*, or *default* when it is absent."""
    return getattr(record, attribute, default)


def _access_records(records, path: str | None = None) -> list:
    """Return the access-log records, optionally for one path only."""
    found = [
        record
        for record in records
        if record.name == ACCESS_LOGGER and _with(record, "status_code") is not None
    ]
    if path is not None:
        found = [record for record in found if _with(record, "path") == path]
    return found


def _access_record(records, path: str | None = None):
    """Return the single access-log record for *path*.

    Fails loudly when there is not exactly one, so a middleware that stops
    logging — or starts logging twice — cannot be mistaken for a pass.
    """
    found = _access_records(records, path)
    assert len(found) == 1, f"expected 1 access record for {path!r}, got {len(found)}"
    return found[0]


def _provider_records(records) -> list:
    """Return the provider-call timing records."""
    return [
        record
        for record in records
        if record.name == PROVIDER_LOGGER
        and _with(record, "provider_duration_ms") is not None
    ]


def _error_records(records) -> list:
    """Return the records that carry an error classification."""
    return [record for record in records if _with(record, "error_code") is not None]


def _classified(records, error_code: str) -> list:
    """Return the records classified as *error_code*."""
    return [record for record in _error_records(records)
            if _with(record, "error_code") == error_code]


def _post(payload: dict, provider, **kwargs) -> httpx.Response:
    """POST *payload* with *provider* standing in for the LLM."""
    with patch("app.main._build_provider", return_value=provider):
        return client.post("/api/v1/code-understanding", json=payload, **kwargs)


def _payload(**overrides) -> dict:
    """A valid analysis payload, with optional field overrides applied."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload.update(overrides)
    return payload


# ===========================================================================
# Correlation
# ===========================================================================


def test_generated_request_id_is_returned_to_the_caller():
    """A caller with no correlation ID of its own still gets one back."""
    response = client.get("/health")

    assert response.headers.get(REQUEST_ID_HEADER)


def test_caller_supplied_request_id_is_reused():
    """An upstream service must be able to join its logs to these.

    Honouring the inbound value is what makes the correlation useful across
    services; rejecting it would force every caller to guess from timing.
    """
    supplied = "upstream-trace-42"

    response = client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_the_reused_request_id_is_what_the_logs_record(caplog):
    """The echoed ID and the ID in the log line must be the same value."""
    supplied = "upstream-trace-42"

    client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    record = _access_record(caplog.records, "/health")
    assert _with(record, "request_id") == supplied


def test_each_request_gets_its_own_request_id():
    """One ID per request, not one per process."""
    first = client.get("/health").headers[REQUEST_ID_HEADER]
    second = client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second


@pytest.mark.parametrize(
    "supplied",
    [
        "has spaces and ; semicolons",
        "quote\"and\\backslash",
        "tab\tand=equals",
        "x" * 129,
        "   ",
    ],
    ids=["spaces_and_semicolons", "quotes", "tab_and_equals", "too_long", "blank"],
)
def test_an_unsafe_request_id_is_replaced_rather_than_echoed(supplied):
    """A caller-controlled header must not reach the logs or response headers.

    The value is interpolated into a log line and into a response header, so a
    value containing whitespace or quoting could corrupt the log stream or the
    response framing.  Rejecting it is the only safe default.
    """
    response = client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != supplied
    assert echoed


@pytest.mark.parametrize("path", ["/health", "/ready"], ids=["health", "ready"])
def test_request_id_is_present_on_health_responses_too(path):
    """Liveness and readiness are the endpoints an operator polls most."""
    response = client.get(path)

    assert response.headers.get(REQUEST_ID_HEADER)


# ===========================================================================
# Access log — service, operation, duration, outcome
# ===========================================================================


def test_access_log_records_service_operation_status_outcome_and_duration(caplog):
    """One line per request must carry the full operational picture."""
    _post(_payload(), static_provider(EXPLANATION_TEXT))

    record = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(record, "service") == SERVICE_NAME
    assert _with(record, "method") == "POST"
    assert _with(record, "path") == "/api/v1/code-understanding"
    assert _with(record, "status_code") == 200
    assert _with(record, "outcome") == "success"
    assert _with(record, "duration_ms") >= 0


def test_request_duration_is_measured_not_placeholder(caplog):
    """A duration that is always zero is worse than none — it looks real."""
    _post(_payload(), static_provider(EXPLANATION_TEXT))

    record = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(record, "duration_ms") > 0


@pytest.mark.parametrize(
    ("expected_status", "expected_outcome", "provider"),
    [
        (200, "success", static_provider(EXPLANATION_TEXT)),
        (502, "server_error", provider_error_provider()),
        (504, "server_error", provider_timeout_provider()),
    ],
    ids=["success", "provider_error", "provider_timeout"],
)
def test_access_log_classifies_the_outcome(caplog, expected_status, expected_outcome, provider):
    """The same endpoint logs a different outcome depending on what happened."""
    response = _post(_payload(), provider)

    assert response.status_code == expected_status
    record = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(record, "status_code") == expected_status
    assert _with(record, "outcome") == expected_outcome


def test_access_log_classifies_a_rejected_request_as_a_client_error(caplog):
    """A 422 is the caller's problem and must not be grouped with a 5xx."""
    response = client.post("/api/v1/code-understanding", json={"language": "python"})

    assert response.status_code == 422
    record = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(record, "status_code") == 422
    assert _with(record, "outcome") == "client_error"


def test_exactly_one_access_line_is_emitted_per_request(caplog):
    """Duplicate lines would double-count every metric derived from them."""
    _post(_payload(), static_provider(EXPLANATION_TEXT))

    assert len(_access_records(caplog.records)) == 1


def test_the_query_string_is_never_logged(caplog):
    """Query strings carry caller-supplied values; only the path is recorded."""
    secret = "TRIPWIRE_QUERY_c93d"

    client.post(
        f"/api/v1/code-understanding?token={secret}",
        json={"language": "python"},
    )

    record = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(record, "path") == "/api/v1/code-understanding"
    assert secret not in _rendered(_engine_records(caplog.records))


def test_the_provider_line_and_the_access_line_share_one_request_id(caplog):
    """Correlation is the join: two lines, one request, one ID."""
    _post(_payload(), static_provider(EXPLANATION_TEXT))

    access = _access_record(caplog.records, "/api/v1/code-understanding")
    provider_records = _provider_records(caplog.records)
    assert len(provider_records) == 1
    provider = provider_records[0]

    assert _with(provider, "request_id") == _with(access, "request_id")
    assert _with(provider, "request_id") not in (None, "-")


# ===========================================================================
# Error classification — the four failures must stay tellable apart
# ===========================================================================


def test_a_rejected_request_is_logged_as_a_validation_error(caplog):
    client.post("/api/v1/code-understanding", json={"language": "python"})

    assert _classified(caplog.records, "VALIDATION_ERROR")


def test_a_provider_failure_is_logged_as_a_provider_error(caplog):
    _post(_payload(), provider_error_provider())

    assert _classified(caplog.records, "PROVIDER_ERROR")


def test_a_provider_timeout_is_logged_as_a_provider_timeout(caplog):
    _post(_payload(), provider_timeout_provider())

    assert _classified(caplog.records, "PROVIDER_TIMEOUT")


def test_an_unbuildable_provider_is_logged_as_provider_unavailable(caplog):
    """Provider construction failing is a different problem from a bad call."""
    with patch("app.main._build_provider", side_effect=RuntimeError("no provider")):
        client.post("/api/v1/code-understanding", json=_payload())

    assert _classified(caplog.records, "PROVIDER_UNAVAILABLE")


def test_an_escaping_exception_is_logged_as_an_internal_error(caplog):
    """Engine failure must be separable from every provider failure."""
    strict_client = TestClient(app, raise_server_exceptions=False)

    with patch("app.main._build_provider", return_value=object()):
        with patch("app.main.OrchestratorService", side_effect=RuntimeError("boom")):
            response = strict_client.post(
                "/api/v1/code-understanding", json=_payload()
            )

    assert response.status_code == 500
    assert _classified(caplog.records, "INTERNAL_ERROR")


def test_each_failure_class_maps_to_its_own_error_code(caplog):
    """The log classification must match the code the caller receives.

    If the log said ``PROVIDER_ERROR`` for a 504, an operator reading only the
    logs would send a caller down the wrong recovery path, so the two are
    asserted together.
    """
    cases = {
        "VALIDATION_ERROR": 422,
        "PROVIDER_ERROR": 502,
        "PROVIDER_UNAVAILABLE": 503,
        "PROVIDER_TIMEOUT": 504,
    }
    providers = {
        "PROVIDER_ERROR": provider_error_provider(),
        "PROVIDER_TIMEOUT": provider_timeout_provider(),
    }

    for error_code, status in cases.items():
        caplog.clear()
        if error_code == "VALIDATION_ERROR":
            response = client.post(
                "/api/v1/code-understanding", json={"language": "python"}
            )
        elif error_code == "PROVIDER_UNAVAILABLE":
            with patch("app.main._build_provider", side_effect=RuntimeError("nope")):
                response = client.post(
                    "/api/v1/code-understanding", json=_payload()
                )
        else:
            response = _post(_payload(), providers[error_code])

        assert response.status_code == status, error_code
        classified = _classified(caplog.records, error_code)
        assert classified, f"{error_code} was not logged"
        access = _access_record(
            caplog.records, "/api/v1/code-understanding"
        )
        assert _with(access, "status_code") == status, error_code


def test_a_provider_failure_names_the_provider_that_failed(caplog):
    """Which upstream failed is the first question asked of any 502."""
    _post(_payload(), provider_error_provider())

    classified = _classified(caplog.records, "PROVIDER_ERROR")
    assert _with(classified[0], "provider") == "fixture"


# ===========================================================================
# Provider-call duration
# ===========================================================================


def test_provider_call_duration_is_recorded_on_success(caplog):
    _post(_payload(), static_provider(EXPLANATION_TEXT))

    records = _provider_records(caplog.records)
    assert len(records) == 1
    assert _with(records[0], "provider_duration_ms") > 0
    assert _with(records[0], "provider_ok") is True
    assert _with(records[0], "provider") == "StaticProvider"


def test_provider_call_duration_is_recorded_on_failure(caplog):
    """The duration of a failed call is the interesting one.

    A provider that stalls is the Phase 13 symptom, and a duration recorded
    only on success would make that failure invisible to timing analysis.
    """
    _post(_payload(), provider_timeout_provider())

    records = _provider_records(caplog.records)
    assert len(records) == 1
    assert _with(records[0], "provider_ok") is False
    assert _with(records[0], "provider_duration_ms") >= 0


def test_a_stalled_provider_shows_up_in_both_durations(monkeypatch, caplog):
    """Total request time and provider time must move together.

    This is the observation that separates "the upstream is slow" from "the
    pipeline around the upstream is slow" — the distinction the Phase 13
    investigation needs and cannot get from a single total.
    """
    install_upstream(
        monkeypatch,
        error=httpx.ReadTimeout(
            "timed out", request=httpx.Request("POST", CHAT_URL)
        ),
    )

    with patch("app.main._build_provider", return_value=ollama_provider()):
        client.post("/api/v1/code-understanding", json=_payload())

    provider = _provider_records(caplog.records)[0]
    access = _access_record(caplog.records, "/api/v1/code-understanding")
    assert _with(provider, "provider_duration_ms") >= 0
    assert _with(access, "duration_ms") >= _with(provider, "provider_duration_ms")


def test_a_refused_connection_is_recorded_as_a_provider_error(monkeypatch, caplog):
    """An unreachable daemon is a provider failure, not a timeout.

    Driven through the real ``OllamaProvider`` and a real transport, so the
    classification comes from the engine's own error translation rather than a
    pre-baked exception.
    """
    install_upstream(monkeypatch, error=connect_error("connection refused"))

    with patch("app.main._build_provider", return_value=ollama_provider()):
        response = client.post(
            "/api/v1/code-understanding", json=_payload()
        )

    assert response.status_code == 502
    assert _classified(caplog.records, "PROVIDER_ERROR")
    assert not _classified(caplog.records, "PROVIDER_TIMEOUT")


# ===========================================================================
# Confidentiality — Phase 33
# ===========================================================================


def test_the_configured_api_key_is_never_written_to_a_log_record(caplog):
    """The key is read from the environment and must never be echoed.

    Driven across a success, a provider failure, and an unconfigured readiness
    check, because "we never log it" has to hold on every path.
    """
    with patch("app.main.settings", replace(Settings(), api_key=SECRET_API_KEY)):
        _post(_payload(), static_provider(EXPLANATION_TEXT))
        _post(_payload(), provider_error_provider())
        client.get("/ready")

    assert SECRET_API_KEY not in _rendered(_engine_records(caplog.records))


def test_submitted_source_code_is_never_written_to_a_log_record(caplog):
    """A code-understanding tool receives source it must not republish.

    Both the submitted snippet and the supplementary context are planted with
    tripwires; a prompt, source, or chunk appearing in any log field fails here.
    """
    payload = _payload(
        source_code=f"def add(a, b):\n    # {SECRET_SOURCE_LINE}\n    return a + b\n",
        context=f"Called from the CLI. {SECRET_CONTEXT_LINE}",
    )

    _post(payload, static_provider(EXPLANATION_TEXT))

    rendered = _rendered(_engine_records(caplog.records))
    assert SECRET_SOURCE_LINE not in rendered
    assert SECRET_CONTEXT_LINE not in rendered


def test_the_provider_call_line_carries_no_prompt_and_no_completion(caplog):
    """The timing line is about latency, not about content."""
    payload = _payload(
        source_code=f"def add(a, b):\n    # {SECRET_SOURCE_LINE}\n    return a + b\n"
    )

    _post(payload, static_provider(EXPLANATION_TEXT))

    record = _provider_records(caplog.records)[0]
    assert SECRET_SOURCE_LINE not in _rendered([record])
    assert EXPLANATION_TEXT not in _rendered([record])


def test_the_model_completion_is_never_written_to_a_log_record(caplog):
    """A completion is the model's answer, not an operational fact."""
    completion = "TRIPWIRE_COMPLETION_d05f"

    _post(_payload(), static_provider(completion))

    assert completion not in _rendered(_engine_records(caplog.records))


def test_an_upstream_error_message_stays_out_of_the_response(caplog):
    """The upstream text is for the operator's log, never the caller's body."""
    secret = "http://internal-host-9f3a.corp:11434 refused sk-live-ABC123"

    response = _post(_payload(), provider_error_provider(secret))

    assert secret not in response.text
    # The operator still gets the reason, which is the point of logging it.
    assert _classified(caplog.records, "PROVIDER_ERROR")


# ===========================================================================
# Liveness and readiness
# ===========================================================================


def test_both_probe_endpoints_are_logged(caplog):
    """A health-check-only deployment still produces a usable log stream."""
    client.get("/health")
    client.get("/ready")

    health = _access_record(caplog.records, "/health")
    ready = _access_record(caplog.records, "/ready")
    assert _with(health, "status_code") == 200
    assert _with(ready, "status_code") == 200
    assert _with(health, "request_id") != _with(ready, "request_id")


def test_an_unconfigured_engine_logs_liveness_and_readiness_differently(caplog):
    """The whole point of the two endpoints, visible in the logs.

    A live-but-not-ready service must be distinguishable from a dead one: the
    first is a configuration problem, the second means the process is gone.
    """
    with patch("app.main.settings", replace(Settings(), provider="")):
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code == 503

    health_record = _access_record(caplog.records, "/health")
    ready_record = _access_record(caplog.records, "/ready")
    assert _with(health_record, "outcome") == "success"
    assert _with(ready_record, "outcome") == "server_error"
    assert _with(ready_record, "status_code") == 503


def test_probe_endpoints_make_no_provider_call():
    """Instrumentation must not turn a probe into a model round-trip."""
    provider = static_provider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.get("/health")
        client.get("/ready")

    assert provider.call_count == 0
