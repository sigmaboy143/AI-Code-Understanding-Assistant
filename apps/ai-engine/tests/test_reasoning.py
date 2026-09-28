"""Tests for the code-understanding reasoning layer (Task 6).

Validates prompt construction, per-analysis instruction injection,
question handling, context handling, and the missing-information reminder.
No real LLM or network access is required.
"""

from __future__ import annotations

import pytest

from app.orchestrator import OrchestratorService
from app.providers.base import LLMProvider, LLMRequest, LLMResponse, ProviderError
from app.reasoning import (
    _ANALYSIS_INSTRUCTIONS,
    _SYSTEM_PROMPT,
    _build_analysis_instructions,
    _format_user_message,
    build_reasoning_request,
)
from app.schemas.code_understanding import (
    AnalysisType,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
    ProgrammingLanguage,
)

SAMPLE_CODE = "def greet(name: str) -> str:\n    return f'Hello, {name}'\n"


def _make_request(**overrides) -> CodeUnderstandingRequest:
    base = {
        "source_code": SAMPLE_CODE,
        "language": "python",
        "analyses": [AnalysisType.EXPLANATION],
    }
    base.update(overrides)
    return CodeUnderstandingRequest(**base)


class _MockProvider(LLMProvider):
    def __init__(self, text: str = "Mocked result.") -> None:
        self.text = text
        self.calls: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(content=self.text)


# ---------------------------------------------------------------------------
# build_reasoning_request — structure
# ---------------------------------------------------------------------------


def test_reasoning_request_has_two_messages():
    req = build_reasoning_request(_make_request())
    assert len(req.messages) == 2


def test_reasoning_request_first_message_is_system():
    req = build_reasoning_request(_make_request())
    assert req.messages[0].role == "system"


def test_reasoning_request_second_message_is_user():
    req = build_reasoning_request(_make_request())
    assert req.messages[1].role == "user"


def test_system_prompt_instructs_not_to_fabricate():
    """The system prompt must explicitly forbid fabrication."""
    req = build_reasoning_request(_make_request())
    system_content = req.messages[0].content
    assert "fabricate" in system_content.lower() or "invent" in system_content.lower()


def test_system_prompt_is_non_trivial():
    req = build_reasoning_request(_make_request())
    assert len(req.messages[0].content) >= 50


# ---------------------------------------------------------------------------
# User message — required fields
# ---------------------------------------------------------------------------


def test_user_message_contains_source_code():
    req = build_reasoning_request(_make_request())
    assert SAMPLE_CODE in req.messages[1].content


def test_user_message_contains_language():
    req = build_reasoning_request(_make_request())
    assert "python" in req.messages[1].content.lower()


def test_user_message_contains_analysis_instruction():
    req = build_reasoning_request(_make_request(analyses=[AnalysisType.EXPLANATION]))
    assert "explanation" in req.messages[1].content.lower()


# ---------------------------------------------------------------------------
# User message — optional fields
# ---------------------------------------------------------------------------


def test_user_message_includes_file_path_when_present():
    req = build_reasoning_request(_make_request(file_path="src/greet.py"))
    assert "src/greet.py" in req.messages[1].content


def test_user_message_omits_file_path_when_absent():
    req = build_reasoning_request(_make_request())
    assert "File:" not in req.messages[1].content


def test_user_message_includes_question_when_present():
    question = "Why does this use f-strings?"
    req = build_reasoning_request(_make_request(question=question))
    assert question in req.messages[1].content


def test_user_message_omits_question_section_when_absent():
    req = build_reasoning_request(_make_request())
    assert "Question" not in req.messages[1].content


def test_user_message_includes_context_when_present():
    ctx = "Called from main.py line 42."
    req = build_reasoning_request(_make_request(context=ctx))
    assert ctx in req.messages[1].content


def test_user_message_omits_context_section_when_absent():
    req = build_reasoning_request(_make_request())
    assert "Additional context" not in req.messages[1].content


# ---------------------------------------------------------------------------
# Analysis instructions
# ---------------------------------------------------------------------------


def test_all_analysis_types_have_instructions():
    """Every AnalysisType must have an entry in _ANALYSIS_INSTRUCTIONS."""
    for at in AnalysisType:
        assert at in _ANALYSIS_INSTRUCTIONS, f"Missing instruction for {at}"


def test_multiple_analysis_types_all_appear_in_prompt():
    analyses = [AnalysisType.EXPLANATION, AnalysisType.STRUCTURE, AnalysisType.IMPROVEMENTS]
    req = build_reasoning_request(_make_request(analyses=analyses))
    content = req.messages[1].content
    for at in analyses:
        assert at.value in content.lower()


def test_analysis_instructions_are_numbered():
    instructions = _build_analysis_instructions(
        [AnalysisType.EXPLANATION, AnalysisType.STRUCTURE]
    )
    assert "1." in instructions
    assert "2." in instructions


def test_single_analysis_instruction():
    instructions = _build_analysis_instructions([AnalysisType.DEPENDENCIES])
    assert "dependencies" in instructions.lower()
    assert "1." in instructions


# ---------------------------------------------------------------------------
# Missing-information reminder
# ---------------------------------------------------------------------------


def test_user_message_contains_missing_info_reminder():
    """The prompt must instruct the model to acknowledge missing information."""
    req = build_reasoning_request(_make_request())
    content = req.messages[1].content
    assert "missing" in content.lower()


# ---------------------------------------------------------------------------
# Provider response → CodeUnderstandingResponse mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reasoning_response_summary_matches_provider_output():
    text = "The greet function returns a greeting string."
    service = OrchestratorService(provider=_MockProvider(text))
    result = await service.analyse(_make_request())
    assert result.summary == text


@pytest.mark.asyncio
async def test_reasoning_response_is_typed():
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())
    assert isinstance(result, CodeUnderstandingResponse)


@pytest.mark.asyncio
async def test_reasoning_response_metadata_language():
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request())
    assert result.metadata.language is ProgrammingLanguage.PYTHON


@pytest.mark.asyncio
async def test_reasoning_response_metadata_analyses():
    analyses = [AnalysisType.STRUCTURE, AnalysisType.DEPENDENCIES]
    service = OrchestratorService(provider=_MockProvider())
    result = await service.analyse(_make_request(analyses=analyses))
    assert set(result.metadata.analyses) == set(analyses)


@pytest.mark.asyncio
async def test_whitespace_only_response_gets_fallback_summary():
    service = OrchestratorService(provider=_MockProvider("   "))
    result = await service.analyse(_make_request())
    assert result.summary.strip()


@pytest.mark.asyncio
async def test_provider_error_propagates():
    class _Fail(LLMProvider):
        async def complete(self, request: LLMRequest) -> LLMResponse:
            raise ProviderError("fail", provider="test")

    service = OrchestratorService(provider=_Fail())
    with pytest.raises(ProviderError):
        await service.analyse(_make_request())


# ---------------------------------------------------------------------------
# Reasoning via orchestrator — uses reasoning layer end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_uses_reasoning_system_prompt():
    """The orchestrator must now send the reasoning system prompt."""
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)
    await service.analyse(_make_request())
    # System prompt from reasoning module must be used.
    assert provider.calls[0].messages[0].content == _SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_orchestrator_prompt_includes_all_analysis_labels():
    analyses = [AnalysisType.EXPLANATION, AnalysisType.IMPROVEMENTS]
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)
    await service.analyse(_make_request(analyses=analyses))
    user_content = provider.calls[0].messages[1].content
    assert "explanation" in user_content.lower()
    assert "improvements" in user_content.lower()


@pytest.mark.asyncio
async def test_orchestrator_prompt_question_appears():
    q = "Does this handle None inputs?"
    provider = _MockProvider()
    service = OrchestratorService(provider=provider)
    await service.analyse(_make_request(question=q))
    assert q in provider.calls[0].messages[1].content
