"""Tests for the Code Explanation Agent (Task 11).

Coverage
--------
- Basic code explanation (with and without provider)
- Question handling — answered and unanswerable
- Context/retrieval usage — chunks appear in evidence
- Missing evidence → UNKNOWN / limited result
- No fabricated facts
- Flow step extraction from code
- Evidence and confidence behaviour
- Empty source code → UNKNOWN
"""

from __future__ import annotations

import pytest

from app.agents.explanation import (
    ExplanationAgent,
    ExplanationContext,
    ExplanationResult,
    FlowStep,
)
from app.context_builder.builder import IncludedChunk
from app.evidence.models import ConfidenceLevel, EvidenceSourceType
from app.providers.mock import MockProvider
from app.schemas.code_understanding import ProgrammingLanguage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(response_text: str = "This function computes a sum.") -> ExplanationAgent:
    return ExplanationAgent(provider=MockProvider(response_text=response_text))


def _make_agent_no_provider() -> ExplanationAgent:
    return ExplanationAgent(provider=None)


def _simple_context(
    source_code: str = "def add(a, b):\n    return a + b",
    question: str | None = None,
) -> ExplanationContext:
    return ExplanationContext(
        source_code=source_code,
        language=ProgrammingLanguage.PYTHON,
        file_path="src/math.py",
        question=question,
    )


def _make_chunk(chunk_id: str = "c1", file_path: str = "src/helpers.py") -> IncludedChunk:
    return IncludedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        content="def helper(): pass",
        relevance_score=0.9,
    )


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------


def test_explanation_agent_can_be_imported():
    assert ExplanationAgent is not None


def test_explanation_context_can_be_imported():
    assert ExplanationContext is not None


def test_explanation_result_can_be_imported():
    assert ExplanationResult is not None


# ---------------------------------------------------------------------------
# 2. Basic code explanation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explain_returns_result():
    agent = _make_agent()
    result = await agent.explain(_simple_context())
    assert isinstance(result, ExplanationResult)


@pytest.mark.asyncio
async def test_explain_overview_non_empty():
    agent = _make_agent("This function adds two numbers.")
    result = await agent.explain(_simple_context())
    assert result.overview
    assert len(result.overview) > 0


@pytest.mark.asyncio
async def test_explain_overview_from_llm():
    agent = _make_agent("This function adds two numbers.")
    result = await agent.explain(_simple_context())
    assert "This function" in result.overview


@pytest.mark.asyncio
async def test_explain_no_provider_returns_deterministic_overview():
    agent = _make_agent_no_provider()
    result = await agent.explain(_simple_context())
    assert result.overview
    assert "python" in result.overview.lower() or "source code" in result.overview.lower()


@pytest.mark.asyncio
async def test_explain_provider_is_called_once():
    provider = MockProvider(response_text="Adds two numbers.")
    agent = ExplanationAgent(provider=provider)
    await agent.explain(_simple_context())
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 3. Question handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_answered_when_llm_provided():
    agent = _make_agent("The function returns the sum of a and b.")
    ctx = _simple_context(question="What does add() return?")
    result = await agent.explain(ctx)
    assert result.question_answer is not None
    assert "UNKNOWN" not in result.question_answer


@pytest.mark.asyncio
async def test_question_unknown_when_no_provider():
    agent = _make_agent_no_provider()
    ctx = _simple_context(question="What does this return?")
    result = await agent.explain(ctx)
    assert result.question_answer is not None
    assert "UNKNOWN" in result.question_answer


@pytest.mark.asyncio
async def test_no_question_answer_is_none_without_question():
    agent = _make_agent()
    result = await agent.explain(_simple_context(question=None))
    assert result.question_answer is None


@pytest.mark.asyncio
async def test_question_unknown_when_no_provider_and_question_asked():
    """When no provider is supplied and a question is asked, question_answer is UNKNOWN."""
    agent = _make_agent_no_provider()
    ctx = _simple_context(question="What does add() do?")
    result = await agent.explain(ctx)
    # The UNKNOWN appears in question_answer, not in limitations
    assert result.question_answer is not None
    assert "UNKNOWN" in result.question_answer


# ---------------------------------------------------------------------------
# 4. Context / retrieval usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieved_chunks_appear_in_evidence():
    chunk = _make_chunk()
    ctx = ExplanationContext(
        source_code="def add(a, b): return a + b",
        language=ProgrammingLanguage.PYTHON,
        retrieved_chunks=[chunk],
    )
    agent = _make_agent()
    result = await agent.explain(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.RETRIEVED_CHUNK in source_types


@pytest.mark.asyncio
async def test_chunk_file_path_preserved_in_evidence():
    chunk = _make_chunk(file_path="src/utils.py")
    ctx = ExplanationContext(
        source_code="def add(a, b): return a + b",
        language=ProgrammingLanguage.PYTHON,
        retrieved_chunks=[chunk],
    )
    agent = _make_agent()
    result = await agent.explain(ctx)
    file_paths = [e.file_path for e in result.confidence.evidence if e.file_path]
    assert "src/utils.py" in file_paths


@pytest.mark.asyncio
async def test_no_chunk_limitation_recorded():
    agent = _make_agent()
    ctx = _simple_context()  # no retrieved_chunks
    result = await agent.explain(ctx)
    found = any("retrieved context chunks" in lim.lower() for lim in result.limitations)
    assert found


@pytest.mark.asyncio
async def test_chunks_in_llm_prompt():
    chunk = _make_chunk()
    ctx = ExplanationContext(
        source_code="def add(a, b): return a + b",
        language=ProgrammingLanguage.PYTHON,
        retrieved_chunks=[chunk],
    )
    provider = MockProvider(response_text="Adds two values.")
    agent = ExplanationAgent(provider=provider)
    await agent.explain(ctx)
    # Chunk file path should appear in the prompt
    assert len(provider.calls) == 1
    user_msg = provider.calls[0].messages[-1].content
    assert "src/helpers.py" in user_msg


# ---------------------------------------------------------------------------
# 5. Missing evidence → UNKNOWN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_source_code_returns_unknown():
    agent = _make_agent()
    ctx = ExplanationContext(
        source_code="   ",
        language=ProgrammingLanguage.PYTHON,
    )
    result = await agent.explain(ctx)
    assert "UNKNOWN" in result.overview
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


@pytest.mark.asyncio
async def test_empty_source_code_has_limitation():
    agent = _make_agent()
    ctx = ExplanationContext(
        source_code="",
        language=ProgrammingLanguage.PYTHON,
    )
    result = await agent.explain(ctx)
    assert result.limitations


@pytest.mark.asyncio
async def test_no_provider_limitation_recorded():
    agent = _make_agent_no_provider()
    result = await agent.explain(_simple_context())
    found = any("No LLM provider" in lim for lim in result.limitations)
    assert found


# ---------------------------------------------------------------------------
# 6. No fabricated facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_git_evidence_fabricated():
    agent = _make_agent()
    result = await agent.explain(_simple_context())
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


@pytest.mark.asyncio
async def test_flow_steps_only_from_visible_code():
    code = "def foo():\n    return 42"
    agent = _make_agent_no_provider()
    ctx = _simple_context(source_code=code)
    result = await agent.explain(ctx)
    # Steps should reference 'foo' (it's in the code) not an invented name
    descriptions = " ".join(s.description for s in result.flow_steps)
    assert "foo" in descriptions
    assert "invented_function" not in descriptions


@pytest.mark.asyncio
async def test_no_invented_modules_in_result():
    agent = _make_agent("Simple addition function.")
    result = await agent.explain(_simple_context())
    # The overview should not mention modules that were never supplied
    assert "os.path" not in result.overview
    assert "sys.argv" not in result.overview


# ---------------------------------------------------------------------------
# 7. Flow step extraction
# ---------------------------------------------------------------------------


def test_flow_steps_detect_function():
    agent = _make_agent_no_provider()
    ctx = ExplanationContext(
        source_code="def compute(x):\n    return x * 2",
        language=ProgrammingLanguage.PYTHON,
    )
    # Use the private method directly for unit testing
    steps = ExplanationAgent._extract_flow_steps(ctx)
    descriptions = " ".join(s.description for s in steps)
    assert "compute" in descriptions


def test_flow_steps_detect_class():
    ctx = ExplanationContext(
        source_code="class MyClass:\n    pass",
        language=ProgrammingLanguage.PYTHON,
    )
    steps = ExplanationAgent._extract_flow_steps(ctx)
    descriptions = " ".join(s.description for s in steps)
    assert "MyClass" in descriptions


def test_flow_steps_detect_return():
    ctx = ExplanationContext(
        source_code="def f():\n    return True",
        language=ProgrammingLanguage.PYTHON,
    )
    steps = ExplanationAgent._extract_flow_steps(ctx)
    descriptions = " ".join(s.description for s in steps)
    assert "Returns" in descriptions or "return" in descriptions.lower()


def test_flow_steps_detect_if():
    ctx = ExplanationContext(
        source_code="if x > 0:\n    pass",
        language=ProgrammingLanguage.PYTHON,
    )
    steps = ExplanationAgent._extract_flow_steps(ctx)
    assert len(steps) >= 1
    assert any("Conditional" in s.description for s in steps)


def test_flow_steps_detect_loop():
    ctx = ExplanationContext(
        source_code="for item in items:\n    pass",
        language=ProgrammingLanguage.PYTHON,
    )
    steps = ExplanationAgent._extract_flow_steps(ctx)
    assert any("Loop" in s.description for s in steps)


def test_flow_steps_empty_for_comment_only_code():
    ctx = ExplanationContext(
        source_code="# Just a comment\n# Another comment",
        language=ProgrammingLanguage.PYTHON,
    )
    steps = ExplanationAgent._extract_flow_steps(ctx)
    assert steps == []


def test_flow_steps_capped_at_twenty():
    # 25 functions defined
    source = "\n".join(f"def func{i}(): pass" for i in range(25))
    ctx = ExplanationContext(source_code=source, language=ProgrammingLanguage.PYTHON)
    steps = ExplanationAgent._extract_flow_steps(ctx)
    assert len(steps) <= 20


# ---------------------------------------------------------------------------
# 8. Evidence and confidence behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_code_evidence_always_present():
    agent = _make_agent()
    result = await agent.explain(_simple_context())
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.SOURCE_CODE in source_types


@pytest.mark.asyncio
async def test_confidence_confirmed_with_source_code():
    agent = _make_agent()
    result = await agent.explain(_simple_context())
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


@pytest.mark.asyncio
async def test_confidence_notes_present():
    agent = _make_agent()
    result = await agent.explain(_simple_context())
    assert result.confidence.notes is not None
    assert len(result.confidence.notes) > 0


@pytest.mark.asyncio
async def test_file_path_preserved_in_evidence():
    agent = _make_agent()
    ctx = _simple_context()
    result = await agent.explain(ctx)
    file_paths = [e.file_path for e in result.confidence.evidence if e.file_path]
    assert "src/math.py" in file_paths


@pytest.mark.asyncio
async def test_flow_steps_have_confidence_levels():
    agent = _make_agent_no_provider()
    ctx = ExplanationContext(
        source_code="def foo():\n    return 1",
        language=ProgrammingLanguage.PYTHON,
    )
    result = await agent.explain(ctx)
    for step in result.flow_steps:
        assert isinstance(step.confidence, ConfidenceLevel)
