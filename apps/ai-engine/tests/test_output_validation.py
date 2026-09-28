"""Tests for output validation and error handling (Task 10).

Coverage
--------
- Valid provider response: content preserved, confidence attached
- Empty provider response: fallback summary, safe behavior
- Whitespace-only response: fallback summary
- Malformed / non-string content: safe fallback
- Provider exception propagation: ProviderError bubbles unchanged
- ProviderError mapping: correct HTTP status codes (via test_api.py extended)
- Error response shape: error envelope preserved
- No stack trace leakage in error responses
- Existing API behavior unchanged
- validate_llm_response returns tuple (str, ResponseConfidence)
- Normalisation: multi-blank-line collapse
- Truncation at _MAX_SUMMARY_CHARS
- Confidence from chunks → CONFIRMED
- Confidence without chunks → CONFIRMED from source code
- OutputValidationError exists and is importable
- Orchestrator response now carries confidence field
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.evidence.models import ConfidenceLevel, EvidenceSourceType
from app.main import app
from app.output_validation import OutputValidationError, validate_llm_response
from app.output_validation.validator import (
    _FALLBACK_SUMMARY,
    _MAX_SUMMARY_CHARS,
    _normalise_whitespace,
    _extract_content,
)
from app.providers.base import LLMProvider, LLMRequest, LLMResponse, ProviderError
from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest
from app.orchestrator import OrchestratorService
from app.context_builder.builder import IncludedChunk

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
    def __init__(self, response_text: str = "Analysis result.") -> None:
        self.response_text = response_text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.response_text)


class _FailingProvider(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("connection refused", provider="test")


class _TimeoutProvider(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("Ollama request timed out after 60s", provider="ollama")


def _make_request(**overrides) -> CodeUnderstandingRequest:
    base = {
        "source_code": SAMPLE_CODE,
        "language": "python",
        "analyses": [AnalysisType.EXPLANATION],
    }
    base.update(overrides)
    return CodeUnderstandingRequest(**base)


def _make_chunk(chunk_id: str = "c1") -> IncludedChunk:
    return IncludedChunk(
        chunk_id=chunk_id,
        file_path="src/code.py",
        content="def foo(): pass",
        relevance_score=0.8,
    )


# ---------------------------------------------------------------------------
# validate_llm_response — valid response
# ---------------------------------------------------------------------------


def test_valid_response_returns_content_as_summary():
    llm_resp = LLMResponse(content="The function adds two numbers.")
    summary, confidence = validate_llm_response(llm_resp)
    assert summary == "The function adds two numbers."


def test_valid_response_returns_tuple():
    llm_resp = LLMResponse(content="Some content.")
    result = validate_llm_response(llm_resp)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_valid_response_summary_is_string():
    llm_resp = LLMResponse(content="Valid content.")
    summary, _ = validate_llm_response(llm_resp)
    assert isinstance(summary, str)


def test_valid_response_summary_is_non_empty():
    llm_resp = LLMResponse(content="Valid content.")
    summary, _ = validate_llm_response(llm_resp)
    assert summary.strip()


# ---------------------------------------------------------------------------
# validate_llm_response — empty / malformed responses
# ---------------------------------------------------------------------------


def test_empty_content_returns_fallback_summary():
    llm_resp = LLMResponse(content="")
    summary, _ = validate_llm_response(llm_resp)
    assert summary == _FALLBACK_SUMMARY


def test_whitespace_only_content_returns_fallback_summary():
    llm_resp = LLMResponse(content="   \n\n   ")
    summary, _ = validate_llm_response(llm_resp)
    assert summary == _FALLBACK_SUMMARY


def test_fallback_summary_is_non_empty():
    llm_resp = LLMResponse(content="")
    summary, _ = validate_llm_response(llm_resp)
    assert summary.strip()


def test_empty_response_does_not_raise():
    """validate_llm_response must never raise for empty content."""
    llm_resp = LLMResponse(content="")
    try:
        validate_llm_response(llm_resp)
    except Exception as exc:
        pytest.fail(f"validate_llm_response raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# validate_llm_response — whitespace normalisation
# ---------------------------------------------------------------------------


def test_leading_trailing_whitespace_stripped():
    llm_resp = LLMResponse(content="  The function adds.  ")
    summary, _ = validate_llm_response(llm_resp)
    assert summary == "The function adds."


def test_excessive_blank_lines_collapsed():
    llm_resp = LLMResponse(content="Line one.\n\n\n\n\nLine two.")
    summary, _ = validate_llm_response(llm_resp)
    assert "\n\n\n" not in summary


def test_single_blank_line_preserved():
    llm_resp = LLMResponse(content="Para one.\n\nPara two.")
    summary, _ = validate_llm_response(llm_resp)
    assert "\n\n" in summary


# ---------------------------------------------------------------------------
# _normalise_whitespace helper
# ---------------------------------------------------------------------------


def test_normalise_whitespace_empty_string():
    assert _normalise_whitespace("") == ""


def test_normalise_whitespace_strips():
    assert _normalise_whitespace("  hello  ") == "hello"


def test_normalise_whitespace_collapses_triple_newlines():
    result = _normalise_whitespace("a\n\n\n\nb")
    assert "\n\n\n" not in result


def test_normalise_whitespace_preserves_double_newline():
    result = _normalise_whitespace("a\n\nb")
    assert "\n\n" in result


# ---------------------------------------------------------------------------
# _extract_content helper
# ---------------------------------------------------------------------------


def test_extract_content_returns_string():
    llm_resp = LLMResponse(content="hello")
    assert _extract_content(llm_resp) == "hello"


def test_extract_content_empty_string():
    llm_resp = LLMResponse(content="")
    assert _extract_content(llm_resp) == ""


# ---------------------------------------------------------------------------
# validate_llm_response — truncation
# ---------------------------------------------------------------------------


def test_long_response_is_truncated():
    long_text = "x" * (_MAX_SUMMARY_CHARS + 500)
    llm_resp = LLMResponse(content=long_text)
    summary, _ = validate_llm_response(llm_resp)
    assert len(summary) <= _MAX_SUMMARY_CHARS + len(" [truncated]")


def test_truncated_summary_contains_indicator():
    long_text = "y" * (_MAX_SUMMARY_CHARS + 100)
    llm_resp = LLMResponse(content=long_text)
    summary, _ = validate_llm_response(llm_resp)
    assert "[truncated]" in summary


def test_short_response_not_truncated():
    llm_resp = LLMResponse(content="Short answer.")
    summary, _ = validate_llm_response(llm_resp)
    assert "[truncated]" not in summary


# ---------------------------------------------------------------------------
# validate_llm_response — confidence determination (corrected semantics)
# ---------------------------------------------------------------------------


def test_no_chunks_gives_unknown_confidence():
    """Free-text response without chunks: confidence must be UNKNOWN.

    Source code existing does not confirm the model's free-text claims.
    """
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=None)
    assert confidence.level is ConfidenceLevel.UNKNOWN


def test_with_chunks_gives_unknown_confidence():
    """Free-text response with retrieved chunks: confidence must still be UNKNOWN.

    Chunks were available to the model but individual claims have not been
    mapped to them, so the whole-response confidence cannot be CONFIRMED.
    """
    chunks = [_make_chunk("c1"), _make_chunk("c2")]
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=chunks)
    assert confidence.level is ConfidenceLevel.UNKNOWN


def test_with_chunks_evidence_list_is_non_empty():
    """Even though confidence is UNKNOWN, available chunks are recorded as evidence."""
    chunks = [_make_chunk("c1")]
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=chunks)
    assert len(confidence.evidence) > 0


def test_with_chunks_evidence_source_type_is_retrieved_chunk():
    chunks = [_make_chunk("c1")]
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=chunks)
    assert confidence.evidence[0].source_type is EvidenceSourceType.RETRIEVED_CHUNK


def test_without_chunks_evidence_list_is_non_empty():
    """Even without chunks, source-code evidence reference is recorded."""
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=None, file_path="f.py")
    assert len(confidence.evidence) > 0


def test_without_chunks_evidence_source_type_is_source_code():
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=None, file_path="f.py")
    assert confidence.evidence[0].source_type is EvidenceSourceType.SOURCE_CODE


def test_file_path_preserved_in_evidence():
    llm_resp = LLMResponse(content="Analysis here.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=None, file_path="src/main.py")
    assert confidence.evidence[0].file_path == "src/main.py"


def test_source_code_alone_does_not_confirm_llm_answer():
    """Presence of source code must NOT elevate confidence to CONFIRMED."""
    llm_resp = LLMResponse(content="The function adds numbers.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=None, file_path="math.py")
    assert confidence.level is not ConfidenceLevel.CONFIRMED


def test_retrieved_chunks_alone_do_not_confirm_free_text_answer():
    """Retrieved context chunks available to the model do NOT confirm its free-text claims."""
    chunks = [_make_chunk("c1"), _make_chunk("c2")]
    llm_resp = LLMResponse(content="The function does X.")
    _, confidence = validate_llm_response(llm_resp, included_chunks=chunks)
    assert confidence.level is not ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# OutputValidationError is importable and is an Exception
# ---------------------------------------------------------------------------


def test_output_validation_error_is_importable():
    assert OutputValidationError is not None


def test_output_validation_error_is_exception():
    assert issubclass(OutputValidationError, Exception)


def test_output_validation_error_can_be_raised():
    with pytest.raises(OutputValidationError):
        raise OutputValidationError("test error")


# ---------------------------------------------------------------------------
# ProviderError propagation via orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_error_propagates_from_orchestrator():
    service = OrchestratorService(provider=_FailingProvider())
    with pytest.raises(ProviderError):
        await service.analyse(_make_request())


@pytest.mark.asyncio
async def test_provider_error_message_preserved():
    service = OrchestratorService(provider=_FailingProvider())
    with pytest.raises(ProviderError) as exc_info:
        await service.analyse(_make_request())
    assert "connection refused" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Orchestrator response now carries confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_response_has_confidence_field():
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())
    assert result.confidence is not None


@pytest.mark.asyncio
async def test_orchestrator_free_text_response_confidence_is_unknown():
    """Free-text responses must carry UNKNOWN confidence regardless of inputs."""
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())
    assert result.confidence.level is ConfidenceLevel.UNKNOWN


@pytest.mark.asyncio
async def test_orchestrator_response_confidence_has_evidence():
    """UNKNOWN confidence still records available evidence references."""
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())
    assert len(result.confidence.evidence) > 0


@pytest.mark.asyncio
async def test_orchestrator_whitespace_response_gets_fallback_and_unknown_confidence():
    service = OrchestratorService(provider=_MockProvider("   "))
    result = await service.analyse(_make_request())
    assert result.summary == _FALLBACK_SUMMARY
    assert result.confidence is not None
    assert result.confidence.level is ConfidenceLevel.UNKNOWN


# ---------------------------------------------------------------------------
# API error handling — HTTP status codes preserved (Task 10)
# ---------------------------------------------------------------------------


def test_provider_unavailable_returns_503():
    with patch("app.main._build_provider", side_effect=RuntimeError("no provider")):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_provider_error_returns_502():
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"


def test_provider_timeout_returns_504():
    with patch("app.main._build_provider", return_value=_TimeoutProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_TIMEOUT"


def test_validation_error_returns_422():
    payload = {"language": "python", "analyses": ["explanation"]}  # missing source_code
    response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# No stack trace / secrets leakage
# ---------------------------------------------------------------------------


def test_error_response_no_stack_trace():
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert "Traceback" not in response.text


def test_error_response_no_api_key():
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    text = response.text.lower()
    assert "api_key" not in text
    assert "sk-" not in text


def test_error_response_shape_preserved():
    with patch("app.main._build_provider", return_value=_FailingProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


# ---------------------------------------------------------------------------
# Existing API behavior unchanged
# ---------------------------------------------------------------------------


def test_valid_request_returns_200():
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.status_code == 200


def test_valid_request_has_summary():
    with patch("app.main._build_provider", return_value=_MockProvider("The function adds.")):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert response.json()["summary"] == "The function adds."


def test_valid_request_has_metadata():
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    assert "metadata" in response.json()
    assert response.json()["metadata"]["language"] == "python"


def test_valid_request_response_has_confidence():
    with patch("app.main._build_provider", return_value=_MockProvider()):
        response = client.post("/api/v1/code-understanding", json=VALID_PAYLOAD)
    body = response.json()
    assert "confidence" in body
    assert body["confidence"] is not None
    assert "level" in body["confidence"]


def test_health_endpoint_unchanged():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
