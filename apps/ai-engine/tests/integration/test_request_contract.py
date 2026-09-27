"""Contract-level integration tests: AI Engine HTTP surface.

Category
--------
**Integration.** These tests drive the real FastAPI application through
``TestClient`` — real routing, real Pydantic validation, real exception
handlers, real serialisation — and replace only the outermost network hop
(the LLM provider) with a deterministic fixture.

Scope
-----
Verifies the *request* side of the public contract:

- the request schema accepts a minimal and a full payload
- invalid payloads are rejected with 422 and the stable error envelope
- the engine forwards source code, language, analyses, question, and context
  into the prompt it hands the provider

Why it exists
-------------
``tests/test_schemas.py`` covers the Pydantic models in isolation and
``tests/test_api.py`` covers individual status codes.  Neither proves that a
payload accepted at the HTTP boundary is actually *assembled into the prompt*
the provider receives.  That join is what this file verifies, and it is the
join that silently breaks when a field is renamed on one side only.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from tests.fixtures import (
    ALL_ANALYSES,
    RecordingProvider,
    dependencies_input,
    explanation_input,
)

client = TestClient(app)

EXPLANATION_TEXT = "The function `add` returns the sum of its two arguments."


def _post(payload: dict, provider: RecordingProvider) -> dict:
    """POST *payload* with *provider* standing in for the LLM, return the body."""
    with patch("app.main._build_provider", return_value=provider):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Request contract — the HTTP boundary accepts what NestJS sends
# ---------------------------------------------------------------------------


def test_minimal_request_payload_is_accepted():
    """source_code + language + one analysis is the smallest valid request."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)

    body = _post(payload, RecordingProvider(EXPLANATION_TEXT))

    assert body["summary"] == EXPLANATION_TEXT


def test_full_request_payload_is_accepted():
    """Every optional field NestJS may send survives the HTTP boundary."""
    request = explanation_input(
        question="What does this function do?",
        context="Called from the CLI entry point.",
    )
    payload = request.model_dump(mode="json")

    body = _post(payload, RecordingProvider(EXPLANATION_TEXT))

    assert body["metadata"]["file_path"] == request.file_path


def test_request_omitting_analyses_gets_engine_default():
    """Omitting `analyses` is valid: the engine applies its own default.

    NestJS omits the field when it has no explicit selection, so this is the
    path that carries most production traffic.  The schema default is all five
    analysis types.
    """
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    del payload["analyses"]

    body = _post(payload, RecordingProvider(EXPLANATION_TEXT))

    assert body["metadata"]["analyses"] == [a.value for a in ALL_ANALYSES]


def test_every_analysis_type_is_accepted_over_http():
    """All five enum values survive validation — no silent coercion."""
    for analysis in ALL_ANALYSES:
        payload = explanation_input(analyses=[analysis]).model_dump(
            mode="json", exclude_none=True
        )

        body = _post(payload, RecordingProvider(EXPLANATION_TEXT))

        assert body["metadata"]["analyses"] == [analysis.value]


# ---------------------------------------------------------------------------
# Request contract — the engine forwards the payload to the provider
# ---------------------------------------------------------------------------


def test_source_code_reaches_the_provider_prompt():
    """The submitted snippet must appear verbatim in the outbound prompt."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(explanation_input().model_dump(mode="json"), provider)

    assert "def add(a, b):" in provider.last_user_message


def test_language_reaches_the_provider_prompt():
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(explanation_input().model_dump(mode="json"), provider)

    assert "Language: python" in provider.last_user_message


def test_requested_analyses_reach_the_provider_prompt():
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        provider,
    )

    assert "[DEPENDENCIES]" in provider.last_user_message


def test_question_reaches_the_provider_prompt():
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(
        explanation_input(question="Why does this return a float?").model_dump(
            mode="json", exclude_none=True
        ),
        provider,
    )

    assert "Why does this return a float?" in provider.last_user_message


def test_context_reaches_the_provider_prompt():
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(
        explanation_input(context="Called from the CLI.").model_dump(mode="json"),
        provider,
    )

    assert "Called from the CLI." in provider.last_user_message


def test_anti_fabrication_instruction_is_always_sent():
    """The system prompt must forbid inventing repository facts on every call.

    This is the single instruction that prevents Git, test, and dependency
    fabrication, so it is asserted at the integration boundary rather than only
    in the reasoning unit tests.
    """
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(explanation_input().model_dump(mode="json"), provider)

    system_prompt = provider.requests[0].messages[0].content
    assert "do not invent" in system_prompt.lower()


def test_provider_is_called_exactly_once_per_request():
    """One request must not fan out into several provider calls."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    _post(explanation_input().model_dump(mode="json"), provider)

    assert provider.call_count == 1


# ---------------------------------------------------------------------------
# Request contract — invalid payloads
# ---------------------------------------------------------------------------


def test_missing_source_code_is_rejected_with_422_envelope():
    response = client.post(
        "/api/v1/code-understanding",
        json={"language": "python", "analyses": ["explanation"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_language_is_rejected_with_422_envelope():
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload["language"] = "brainfuck"

    response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_field_is_rejected_with_422_envelope():
    """`extra="forbid"` protects the contract from silent field drift."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload["temperature"] = 0.2

    response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 422


def test_empty_analyses_list_is_rejected_with_422_envelope():
    """NestJS must never send `[]`; the engine documents it as a 422."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload["analyses"] = []

    response = client.post("/api/v1/code-understanding", json=payload)

    assert response.status_code == 422
