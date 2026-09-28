"""Tests for the POST /api/v1/code-understanding endpoint (Task 5).

All tests use TestClient with a patched provider — no real LLM is required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.providers.base import LLMProvider, LLMRequest, LLMResponse, ProviderError
from app.schemas.code_understanding import AnalysisType

client = TestClient(app)

SAMPLE_CODE = "def add(a, b):\n    return a + b\n"

VALID_PAYLOAD = {
    "source_code": SAMPLE_CODE,
    "language": "python",
    "analyses": ["explanation"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockProvider(LLMProvider):
    """Deterministic mock — returns a fixed response."""

    def __init__(self, response_text: str = "This function adds two numbers.") -> None:
        self.response_text = response_text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.response_text)


class _FailingProvider(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("connection refused", provider="test")


class _TimeoutProvider(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("Ollama request timed out after 60s", provider="ollama")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /ready
# ---------------------------------------------------------------------------


def test_ready_returns_ready_when_provider_is_ollama():
    """Default settings (PROVIDER=ollama) satisfy is_configured → 200."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.is_configured = True
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_not_configured():
    with patch("app.main.settings") as mock_settings:
        mock_settings.is_configured = False
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"


# ---------------------------------------------------------------------------
# POST /api/v1/code-understanding — valid request
# ---------------------------------------------------------------------------


def test_code_understanding_valid_request_returns_200():
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 200


def test_code_understanding_response_has_summary():
    with patch("app.main._build_provider", return_value=_MockProvider("The function adds two numbers.")):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    body = response.json()
    assert "summary" in body
    assert body["summary"] == "The function adds two numbers."


def test_code_understanding_response_has_metadata():
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    body = response.json()
    assert "metadata" in body
    assert body["metadata"]["language"] == "python"


def test_code_understanding_with_question():
    payload = {**VALID_PAYLOAD, "question": "What does this function do?"}
    with patch("app.main._build_provider", return_value=_MockProvider("It adds two numbers.")):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200
    assert response.json()["summary"] == "It adds two numbers."


def test_code_understanding_with_file_path():
    payload = {**VALID_PAYLOAD, "file_path": "src/math.py"}
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body["metadata"]["file_path"] == "src/math.py"


def test_code_understanding_with_optional_context():
    payload = {**VALID_PAYLOAD, "context": "TypeError was raised on line 1."}
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200


def test_code_understanding_multiple_analyses():
    payload = {**VALID_PAYLOAD, "analyses": ["explanation", "improvements"]}
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert set(body["metadata"]["analyses"]) == {"explanation", "improvements"}


# ---------------------------------------------------------------------------
# POST /api/v1/code-understanding — invalid request → 422
# ---------------------------------------------------------------------------


def test_missing_source_code_returns_422():
    payload = {"language": "python", "analyses": ["explanation"]}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_missing_language_returns_422():
    payload = {"source_code": SAMPLE_CODE, "analyses": ["explanation"]}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_blank_source_code_returns_422():
    payload = {"source_code": "   ", "language": "python", "analyses": ["explanation"]}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422


def test_unknown_language_returns_422():
    payload = {"source_code": SAMPLE_CODE, "language": "brainfuck", "analyses": ["explanation"]}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422


def test_unknown_analysis_type_returns_422():
    payload = {"source_code": SAMPLE_CODE, "language": "python", "analyses": ["astrology"]}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422


def test_empty_analyses_list_returns_422():
    payload = {"source_code": SAMPLE_CODE, "language": "python", "analyses": []}
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/code-understanding — error status code mapping
# ---------------------------------------------------------------------------


def test_provider_unavailable_returns_503():
    """When _build_provider raises, the response is 503 PROVIDER_UNAVAILABLE."""
    with patch("app.main._build_provider", side_effect=RuntimeError("no provider")):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_provider_error_returns_502():
    """ProviderError (non-timeout) maps to 502 PROVIDER_ERROR."""
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_ERROR"


def test_provider_timeout_returns_504():
    """ProviderError with 'timeout' in message maps to 504 PROVIDER_TIMEOUT."""
    with patch("app.main._build_provider", return_value=_TimeoutProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_TIMEOUT"


def test_error_response_does_not_expose_secrets():
    """Error responses must not contain API keys or stack traces."""
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    text = response.text
    assert "sk-" not in text
    assert "Traceback" not in text
    assert "api_key" not in text.lower()


def test_error_response_shape():
    """Every error uses the standard envelope: {"error": {"code": ..., "message": ...}}."""
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]
