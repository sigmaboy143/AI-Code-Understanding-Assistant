"""Unit tests for the AI Orchestrator (Task 4).

All tests use a deterministic mock provider — no network access is required.

Test coverage
-------------
1. Orchestrator can be imported.
2. Orchestrator accepts a valid CodeUnderstandingRequest.
3. Orchestrator calls the provider abstraction.
4. Provider messages are constructed correctly.
5. Provider output is converted into the expected typed result.
6. Provider errors are propagated predictably.
7. The orchestrator works with a mock provider without network access.
8. Existing Task 1 and Task 2 tests are unaffected (run in same suite).
"""

from __future__ import annotations

import pytest

from app.orchestrator import OrchestratorService
from app.providers.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse, ProviderError
from app.schemas import (
    AnalysisType,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
    ProgrammingLanguage,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SAMPLE_CODE = "def greet(name: str) -> str:\n    return f'Hello, {name}'\n"


def _make_request(**overrides) -> CodeUnderstandingRequest:
    """Return a minimal valid request, optionally overriding fields."""
    base = {
        "source_code": SAMPLE_CODE,
        "language": "python",
        "analyses": [AnalysisType.EXPLANATION],
    }
    base.update(overrides)
    return CodeUnderstandingRequest(**base)


class _MockProvider(LLMProvider):
    """Deterministic mock provider — records calls and returns a fixed reply."""

    def __init__(self, response_text: str = "Mock analysis result.") -> None:
        self.response_text = response_text
        self.calls: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(content=self.response_text)


class _FailingProvider(LLMProvider):
    """Mock provider that always raises a ProviderError."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("connection refused", provider="mock-failing")


# ---------------------------------------------------------------------------
# 1. Import test
# ---------------------------------------------------------------------------


def test_orchestrator_can_be_imported():
    """OrchestratorService and provider primitives import without error."""
    assert OrchestratorService is not None
    assert LLMProvider is not None
    assert LLMRequest is not None
    assert LLMResponse is not None
    assert ProviderError is not None


# ---------------------------------------------------------------------------
# 2. Construction
# ---------------------------------------------------------------------------


def test_orchestrator_accepts_mock_provider():
    """OrchestratorService can be constructed with any LLMProvider."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)
    assert service is not None


# ---------------------------------------------------------------------------
# 3. Orchestrator calls the provider abstraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_calls_provider_once():
    """analyse() calls provider.complete() exactly once per request."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request())

    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 4. Provider messages are constructed correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_start_with_system_prompt():
    """The first message sent to the provider must be the system prompt."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request())

    llm_req = provider.calls[0]
    assert llm_req.messages[0].role == "system"
    assert len(llm_req.messages[0].content) > 0


@pytest.mark.asyncio
async def test_messages_contain_user_message():
    """A user message follows the system prompt."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request())

    llm_req = provider.calls[0]
    assert llm_req.messages[1].role == "user"


@pytest.mark.asyncio
async def test_user_message_contains_source_code():
    """The user message includes the submitted source code."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request())

    user_content = provider.calls[0].messages[1].content
    assert SAMPLE_CODE in user_content


@pytest.mark.asyncio
async def test_user_message_contains_language():
    """The user message includes the language identifier."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request())

    user_content = provider.calls[0].messages[1].content
    assert "python" in user_content.lower()


@pytest.mark.asyncio
async def test_user_message_includes_file_path_when_provided():
    """If file_path is set, it appears in the user message."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request(file_path="src/greet.py"))

    user_content = provider.calls[0].messages[1].content
    assert "src/greet.py" in user_content


@pytest.mark.asyncio
async def test_user_message_includes_question_when_provided():
    """If a question is given, it appears in the user message."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request(question="Why does this use f-strings?"))

    user_content = provider.calls[0].messages[1].content
    assert "Why does this use f-strings?" in user_content


@pytest.mark.asyncio
async def test_user_message_includes_context_when_provided():
    """If additional context is given, it appears in the user message."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    await service.analyse(_make_request(context="Called from main.py line 42."))

    user_content = provider.calls[0].messages[1].content
    assert "Called from main.py line 42." in user_content


@pytest.mark.asyncio
async def test_user_message_includes_all_requested_analysis_types():
    """Every requested analysis type is mentioned in the user message."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)

    analyses = [AnalysisType.EXPLANATION, AnalysisType.IMPROVEMENTS]
    await service.analyse(_make_request(analyses=analyses))

    user_content = provider.calls[0].messages[1].content
    assert "explanation" in user_content
    assert "improvements" in user_content


# ---------------------------------------------------------------------------
# 5. Provider output is converted into the expected typed result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyse_returns_code_understanding_response():
    """analyse() returns a CodeUnderstandingResponse instance."""
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())

    assert isinstance(result, CodeUnderstandingResponse)


@pytest.mark.asyncio
async def test_response_summary_matches_provider_output():
    """The response summary is taken from the provider's completion text."""
    expected = "The function greets the caller by name."
    service = OrchestratorService(provider=_MockProvider(response_text=expected))

    result = await service.analyse(_make_request())

    assert result.summary == expected


@pytest.mark.asyncio
async def test_response_metadata_language_matches_request():
    """Metadata carries the language from the original request."""
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())

    assert result.metadata.language is ProgrammingLanguage.PYTHON


@pytest.mark.asyncio
async def test_response_metadata_file_path_matches_request():
    """Metadata carries the file_path from the request when supplied."""
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request(file_path="app/greeter.py"))

    assert result.metadata.file_path == "app/greeter.py"


@pytest.mark.asyncio
async def test_response_metadata_analyses_match_request():
    """Metadata lists exactly the analysis types that were requested."""
    analyses = [AnalysisType.STRUCTURE, AnalysisType.DEPENDENCIES]
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request(analyses=analyses))

    assert set(result.metadata.analyses) == set(analyses)


@pytest.mark.asyncio
async def test_whitespace_only_provider_response_gets_fallback_summary():
    """If provider returns only whitespace, a fallback summary is used."""
    service = OrchestratorService(provider=_MockProvider(response_text="   "))
    result = await service.analyse(_make_request())

    assert result.summary  # must be non-empty
    assert result.summary.strip()


# ---------------------------------------------------------------------------
# 6. Provider errors are propagated predictably
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_error_propagates_as_provider_error():
    """ProviderError raised inside the provider bubbles up unchanged."""
    service = OrchestratorService(provider=_FailingProvider())

    with pytest.raises(ProviderError) as exc_info:
        await service.analyse(_make_request())

    assert "connection refused" in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_error_preserves_provider_attribute():
    """ProviderError.provider attribute is preserved after propagation."""
    service = OrchestratorService(provider=_FailingProvider())

    with pytest.raises(ProviderError) as exc_info:
        await service.analyse(_make_request())

    assert exc_info.value.provider == "mock-failing"


# ---------------------------------------------------------------------------
# 7. No network access — mock provider is pure in-process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_provider_requires_no_network():
    """The full analyse() round-trip completes with zero I/O using the mock."""
    # If this test passes, the orchestrator works without any real LLM service.
    service = OrchestratorService(provider=_MockProvider("Pure in-process result."))
    result = await service.analyse(_make_request())

    assert result.summary == "Pure in-process result."


# ---------------------------------------------------------------------------
# Provider interface / model tests
# ---------------------------------------------------------------------------


def test_llm_request_requires_at_least_one_message():
    """LLMRequest rejects an empty message list."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LLMRequest(messages=[])


def test_llm_message_rejects_invalid_role():
    """LLMMessage rejects roles other than system/user/assistant."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LLMMessage(role="moderator", content="hello")


def test_llm_request_accepts_optional_temperature():
    """LLMRequest stores an optional temperature."""
    req = LLMRequest(
        messages=[LLMMessage(role="user", content="hello")],
        temperature=0.7,
    )
    assert req.temperature == pytest.approx(0.7)


def test_provider_error_stores_message_and_provider():
    """ProviderError stores human-readable message and provider name."""
    err = ProviderError("timeout", provider="ollama")
    assert str(err) == "timeout"
    assert err.provider == "ollama"


def test_provider_error_provider_defaults_to_none():
    """ProviderError.provider defaults to None when not given."""
    err = ProviderError("unknown failure")
    assert err.provider is None
