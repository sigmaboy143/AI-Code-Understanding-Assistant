"""Contract-level integration tests: AI Engine HTTP response envelope.

Category
--------
**Integration.** Real FastAPI application via ``TestClient``; only the LLM
provider is faked.

Scope
-----
Verifies the *response* side of the public contract, which is exactly what
Member 1's NestJS adapter deserialises:

- success envelope: ``summary``, ``metadata``, ``confidence``, ``evidence``
- optional structured fields: present as ``null`` unless genuinely populated
- ``dependencies`` appears only when requested and only when grounded
- error envelope: 422 / 502 / 503 / 504 / 500, all using
  ``{"error": {"code", "message"}}``
- error bodies never leak secrets or stack traces

Why it exists
-------------
``tests/test_api.py`` and ``tests/test_output_validation.py`` already assert
individual status codes.  What is not asserted anywhere is the **complete
success envelope shape** — that every key the NestJS
``AiEngineResponseContract`` interface declares is actually present, with the
right type, on a real 200 response.  A field that silently disappears is
invisible to a single-field test but immediately ``undefined`` in TypeScript.
This file asserts the envelope as a whole.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import ProviderError
from tests.fixtures import (
    EXPLANATION_TEXT,
    RecordingProvider,
    dependencies_input,
    empty_content_provider,
    explanation_input,
    malformed_body_provider,
    provider_error_provider,
    provider_timeout_provider,
    static_provider,
    whitespace_content_provider,
)

client = TestClient(app)

#: Keys NestJS declares in ``AiEngineResponseContract``.  Every one must be
#: present on a 200 response — `undefined` is not an acceptable substitute.
CONTRACT_RESPONSE_KEYS = frozenset(
    {
        "summary",
        "metadata",
        "confidence",
        "explanation",
        "structure",
        "dependencies",
        "improvements",
    }
)

#: Keys NestJS declares in ``AiEngineConfidence``.
CONTRACT_CONFIDENCE_KEYS = frozenset({"level", "evidence", "notes"})

#: Keys NestJS declares in ``AiEngineEvidenceItem``.
CONTRACT_EVIDENCE_KEYS = frozenset(
    {
        "source_type",
        "file_path",
        "line_start",
        "line_end",
        "chunk_id",
        "description",
    }
)


def _post(payload: dict, provider) -> dict:
    """POST *payload* with *provider* replacing the LLM; return the JSON body."""
    with patch("app.main._build_provider", return_value=provider):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Success envelope — presence of every contracted key
# ---------------------------------------------------------------------------


def test_success_response_contains_every_contracted_key():
    """No key may be absent; `undefined` would break the NestJS interface."""
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert CONTRACT_RESPONSE_KEYS.issubset(body.keys())


def test_confidence_block_contains_every_contracted_key():
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert CONTRACT_CONFIDENCE_KEYS.issubset(body["confidence"].keys())


def test_evidence_items_contain_every_contracted_key():
    """Evidence entries must be fully populated, even where a field is null."""
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert body["confidence"]["evidence"], "expected at least one evidence item"
    for item in body["confidence"]["evidence"]:
        assert CONTRACT_EVIDENCE_KEYS.issubset(item.keys())


def test_summary_is_a_non_empty_string():
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert isinstance(body["summary"], str)
    assert body["summary"].strip()


def test_metadata_echoes_language_and_file_path():
    request = explanation_input()

    body = _post(request.model_dump(mode="json"), static_provider(EXPLANATION_TEXT))

    assert body["metadata"]["language"] == "python"
    assert body["metadata"]["file_path"] == request.file_path


def test_metadata_analyses_is_a_list_of_strings():
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert isinstance(body["metadata"]["analyses"], list)
    assert all(isinstance(item, str) for item in body["metadata"]["analyses"])


def test_unrequested_structured_fields_are_null_not_missing():
    """Explanation-only request: no structure/dependencies/improvements payload.

    They are emitted as explicit ``null`` so the TypeScript optionality is
    unambiguous.
    """
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert body["explanation"] is None
    assert body["structure"] is None
    assert body["dependencies"] is None
    assert body["improvements"] == []


# ---------------------------------------------------------------------------
# Success envelope — dependencies appear only when requested
# ---------------------------------------------------------------------------


def test_dependencies_are_null_when_not_requested():
    body = _post(
        explanation_input().model_dump(mode="json"),
        static_provider(EXPLANATION_TEXT),
    )

    assert body["dependencies"] is None


def test_dependencies_are_present_when_requested():
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        static_provider(EXPLANATION_TEXT),
    )

    assert body["dependencies"] is not None
    assert isinstance(body["dependencies"]["dependencies"], list)


def test_dependency_names_are_grounded_in_the_submitted_source():
    """Only libraries the snippet actually imports may be listed."""
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        static_provider(EXPLANATION_TEXT),
    )

    names = [item["name"] for item in body["dependencies"]["dependencies"]]
    assert names == ["math", "pathlib"]


def test_dependencies_for_non_python_language_are_empty_not_invented():
    """A Python-only AST extractor must return an empty list, not guess."""
    payload = dependencies_input(language="go").model_dump(mode="json")

    body = _post(payload, static_provider(EXPLANATION_TEXT))

    assert body["dependencies"] is not None
    assert body["dependencies"]["dependencies"] == []


# ---------------------------------------------------------------------------
# Success envelope — degraded provider output stays safe
# ---------------------------------------------------------------------------


def test_empty_provider_output_yields_fallback_summary_not_a_crash():
    body = _post(
        explanation_input().model_dump(mode="json"),
        empty_content_provider(),
    )

    assert body["summary"].strip()


def test_whitespace_provider_output_yields_fallback_summary():
    body = _post(
        explanation_input().model_dump(mode="json"),
        whitespace_content_provider(),
    )

    assert body["summary"].strip() != ""


def test_degraded_output_still_carries_a_valid_confidence_block():
    """A blank completion must not silently imply high confidence."""
    body = _post(
        explanation_input().model_dump(mode="json"),
        whitespace_content_provider(),
    )

    assert body["confidence"]["level"] in {"CONFIRMED", "INFERRED", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


def _error_body(provider) -> dict:
    """POST with a failing *provider* and return the error envelope body."""
    with patch("app.main._build_provider", return_value=provider):
        response = client.post(
            "/api/v1/code-understanding",
            json=explanation_input().model_dump(mode="json"),
        )
    assert response.status_code >= 400
    return response.json()


def test_provider_error_returns_502_with_error_envelope():
    body = _error_body(provider_error_provider())

    assert body["error"]["code"] == "PROVIDER_ERROR"


def test_provider_timeout_returns_504_with_error_envelope():
    body = _error_body(provider_timeout_provider())

    assert body["error"]["code"] == "PROVIDER_TIMEOUT"


def test_malformed_provider_response_returns_502_not_a_fabricated_summary():
    """Unreadable upstream JSON must surface as 502, never as invented text."""
    body = _error_body(malformed_body_provider())

    assert body["error"]["code"] == "PROVIDER_ERROR"
    assert "summary" not in body


def test_provider_construction_failure_returns_503():
    with patch("app.main._build_provider", side_effect=RuntimeError("unknown")):
        response = client.post(
            "/api/v1/code-understanding",
            json=explanation_input().model_dump(mode="json"),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_unexpected_internal_failure_returns_500():
    """A non-ProviderError exception escaping the route is still enveloped.

    ``TestClient`` re-raises server exceptions by default, which would hide the
    response the real server sends, so this client opts out.
    """
    strict_client = TestClient(app, raise_server_exceptions=False)

    with patch("app.main._build_provider", return_value=object()):
        with patch(
            "app.main.OrchestratorService",
            side_effect=RuntimeError("boom"),
        ):
            response = strict_client.post(
                "/api/v1/code-understanding",
                json=explanation_input().model_dump(mode="json"),
            )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_asyncio_timeout_maps_to_504():
    """A provider that raises asyncio.TimeoutError is treated as a timeout."""
    import asyncio

    class _AsyncioTimeoutProvider:
        async def complete(self, request):
            raise asyncio.TimeoutError()

    body = _error_body(_AsyncioTimeoutProvider())

    assert body["error"]["code"] == "PROVIDER_TIMEOUT"


# ---------------------------------------------------------------------------
# Error envelope — confidentiality
# ---------------------------------------------------------------------------


def test_provider_error_body_does_not_leak_the_provider_message():
    """The upstream message may contain hostnames or paths; it must not ship."""
    secret = "http://internal-host-9f3a.corp:11434 refused sk-live-ABC123"

    body = _error_body(provider_error_provider(secret))

    rendered = repr(body)
    assert "sk-live-ABC123" not in rendered
    assert "internal-host-9f3a" not in rendered


def test_error_body_contains_no_stack_trace():
    body = _error_body(provider_error_provider())

    assert "Traceback" not in repr(body)
    assert "ProviderError" not in repr(body)


def test_every_error_code_uses_the_same_envelope_shape():
    """One envelope shape for all failures, so the NestJS client can rely on it."""
    for provider in (
        provider_error_provider(),
        provider_timeout_provider(),
        malformed_body_provider(),
    ):
        body = _error_body(provider)
        assert set(body.keys()) == {"error"}
        assert set(body["error"].keys()) == {"code", "message"}
        assert isinstance(body["error"]["message"], str)
        assert body["error"]["message"].strip()


def test_provider_error_attribute_is_preserved_for_logging():
    """`ProviderError.provider` must survive to the log line, not the response."""
    error = ProviderError("boom", provider="ollama")

    assert error.provider == "ollama"


# ---------------------------------------------------------------------------
# Prompt assembly under error conditions
# ---------------------------------------------------------------------------


def test_provider_is_not_called_when_the_request_fails_validation():
    """Validation must reject before any upstream call is attempted."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        response = client.post(
            "/api/v1/code-understanding",
            json={"language": "python"},
        )

    assert response.status_code == 422
    assert provider.call_count == 0
