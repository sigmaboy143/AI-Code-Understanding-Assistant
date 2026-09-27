"""Tests for the Debug and Impact Analysis Agent (Task 13).

Coverage
--------
DEBUG ANALYSIS:
- Debug with stack trace + code
- Insufficient debug evidence
- Root cause from error message
- No fabricated dependencies or causes
- Evidence and confidence behaviour
- LLM provider integration

IMPACT ANALYSIS:
- Impact with supplied relationships (direct + indirect)
- Impact without relationships → UNKNOWN
- Related tests from supplied context
- No fabricated dependencies
- Evidence and confidence behaviour
"""

from __future__ import annotations

import pytest

from app.agents.debug_impact import (
    ComponentRelationship,
    DebugAgent,
    DebugContext,
    DebugResult,
    ImpactAgent,
    ImpactContext,
    ImpactResult,
)
from app.context_builder.builder import IncludedChunk
from app.evidence.models import ConfidenceLevel, EvidenceSourceType
from app.providers.mock import MockProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_debug_agent(response_text: str = "Root cause: None dereference.") -> DebugAgent:
    return DebugAgent(provider=MockProvider(response_text=response_text))


def _make_debug_agent_no_provider() -> DebugAgent:
    return DebugAgent(provider=None)


def _make_impact_agent() -> ImpactAgent:
    return ImpactAgent()


def _simple_debug_ctx(
    error: str = "AttributeError: 'NoneType' object has no attribute 'strip'",
    stack: str | None = None,
    code: str | None = None,
) -> DebugContext:
    return DebugContext(
        error_message=error,
        stack_trace=stack,
        source_code=code,
    )


_SAMPLE_STACK = """\
Traceback (most recent call last):
  File "src/processor.py", line 42, in process
    result = value.strip()
AttributeError: 'NoneType' object has no attribute 'strip'"""

_SAMPLE_CODE = """\
def process(value):
    result = value.strip()
    return result"""


def _make_chunk(chunk_id: str = "c1", file_path: str = "src/helpers.py") -> IncludedChunk:
    return IncludedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        content="def helper(): pass",
        relevance_score=0.9,
    )


def _relationships() -> list[ComponentRelationship]:
    return [
        ComponentRelationship(source="AuthController", target="UserService", kind="dependency"),
        ComponentRelationship(source="OrderService", target="UserService", kind="dependency"),
        ComponentRelationship(source="AdminPanel", target="AuthController", kind="dependency"),
    ]


# ===========================================================================
# A. DEBUG ANALYSIS TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------


def test_debug_agent_can_be_imported():
    assert DebugAgent is not None


def test_debug_context_can_be_imported():
    assert DebugContext is not None


def test_debug_result_can_be_imported():
    assert DebugResult is not None


# ---------------------------------------------------------------------------
# 2. Debug with stack trace + code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debug_returns_result():
    agent = _make_debug_agent()
    result = await agent.analyse(_simple_debug_ctx(stack=_SAMPLE_STACK, code=_SAMPLE_CODE))
    assert isinstance(result, DebugResult)


@pytest.mark.asyncio
async def test_error_summary_non_empty():
    agent = _make_debug_agent()
    result = await agent.analyse(_simple_debug_ctx())
    assert result.error_summary
    assert len(result.error_summary) > 0


@pytest.mark.asyncio
async def test_error_summary_contains_error_text():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(error="TypeError: unsupported operand type")
    result = await agent.analyse(ctx)
    assert "TypeError" in result.error_summary


@pytest.mark.asyncio
async def test_stack_trace_locations_extracted():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK, code=_SAMPLE_CODE)
    result = await agent.analyse(ctx)
    assert len(result.likely_locations) > 0


@pytest.mark.asyncio
async def test_stack_trace_location_has_file_path():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK)
    result = await agent.analyse(ctx)
    file_paths = [loc.file_path for loc in result.likely_locations if loc.file_path]
    assert any("processor.py" in fp for fp in file_paths)


@pytest.mark.asyncio
async def test_stack_trace_location_confidence_confirmed():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK)
    result = await agent.analyse(ctx)
    confirmed = [loc for loc in result.likely_locations if loc.confidence == ConfidenceLevel.CONFIRMED]
    assert len(confirmed) > 0


@pytest.mark.asyncio
async def test_root_cause_from_llm_when_provider_supplied():
    agent = _make_debug_agent(response_text="The value is None because it was not initialised.")
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK, code=_SAMPLE_CODE)
    result = await agent.analyse(ctx)
    assert "None" in result.root_cause or "initialised" in result.root_cause


@pytest.mark.asyncio
async def test_investigation_steps_non_empty():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK, code=_SAMPLE_CODE)
    result = await agent.analyse(ctx)
    assert len(result.investigation_steps) > 0


@pytest.mark.asyncio
async def test_provider_called_once():
    provider = MockProvider(response_text="Root cause found.")
    agent = DebugAgent(provider=provider)
    await agent.analyse(_simple_debug_ctx())
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 3. Insufficient debug evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_message_only_produces_unknown_or_inferred_root_cause():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx()  # No stack, no code
    result = await agent.analyse(ctx)
    # Without stack trace and code, root cause should be UNKNOWN
    assert "UNKNOWN" in result.root_cause or "INFERRED" in result.root_cause


@pytest.mark.asyncio
async def test_no_stack_limitation_recorded():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx()  # No stack
    result = await agent.analyse(ctx)
    found = any("stack trace" in lim.lower() for lim in result.limitations)
    assert found


@pytest.mark.asyncio
async def test_no_code_limitation_recorded():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx()  # No code
    result = await agent.analyse(ctx)
    found = any("source code" in lim.lower() or "retrieved context" in lim.lower() for lim in result.limitations)
    assert found


@pytest.mark.asyncio
async def test_no_provider_limitation_recorded():
    agent = _make_debug_agent_no_provider()
    result = await agent.analyse(_simple_debug_ctx())
    found = any("No LLM provider" in lim for lim in result.limitations)
    assert found


@pytest.mark.asyncio
async def test_confidence_unknown_with_error_message_only():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx()  # No stack, no code
    result = await agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


@pytest.mark.asyncio
async def test_confidence_inferred_with_stack_only():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK)  # No code
    result = await agent.analyse(ctx)
    # Stack trace is present, no code → INFERRED
    assert result.confidence.level in (ConfidenceLevel.INFERRED, ConfidenceLevel.CONFIRMED)


@pytest.mark.asyncio
async def test_confidence_confirmed_with_stack_and_code():
    agent = _make_debug_agent()
    ctx = _simple_debug_ctx(stack=_SAMPLE_STACK, code=_SAMPLE_CODE)
    result = await agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# 4. Retrieved chunks in debug context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieved_chunks_appear_in_evidence():
    chunk = _make_chunk()
    ctx = DebugContext(
        error_message="ValueError: invalid value",
        retrieved_chunks=[chunk],
    )
    agent = _make_debug_agent()
    result = await agent.analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.RETRIEVED_CHUNK in source_types


# ---------------------------------------------------------------------------
# 5. No fabricated dependencies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_git_evidence_fabricated():
    agent = _make_debug_agent()
    result = await agent.analyse(_simple_debug_ctx())
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


@pytest.mark.asyncio
async def test_root_cause_not_invented_without_evidence():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx(error="SomeError: something went wrong")
    result = await agent.analyse(ctx)
    # Should not invent a specific root cause; should say UNKNOWN or INFERRED
    assert "UNKNOWN" in result.root_cause or "INFERRED" in result.root_cause


@pytest.mark.asyncio
async def test_no_fabricated_file_paths_in_locations():
    """Without stack trace, no file paths should be fabricated in locations."""
    agent = _make_debug_agent_no_provider()
    ctx = DebugContext(error_message="RuntimeError: something broke")
    result = await agent.analyse(ctx)
    # No file paths should be in locations since no stack trace or file_path supplied
    file_paths = [loc.file_path for loc in result.likely_locations if loc.file_path]
    assert file_paths == []


# ---------------------------------------------------------------------------
# 6. AttributeError / TypeError heuristic root causes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribute_error_deterministic_inference():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx(error="AttributeError: 'NoneType' object has no attribute 'x'")
    result = await agent.analyse(ctx)
    assert "AttributeError" in result.root_cause or "attribute" in result.root_cause.lower()


@pytest.mark.asyncio
async def test_type_error_deterministic_inference():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx(error="TypeError: unsupported operand type(s) for +")
    result = await agent.analyse(ctx)
    assert "TypeError" in result.root_cause or "type" in result.root_cause.lower()


@pytest.mark.asyncio
async def test_key_error_deterministic_inference():
    agent = _make_debug_agent_no_provider()
    ctx = _simple_debug_ctx(error="KeyError: 'missing_key'")
    result = await agent.analyse(ctx)
    assert "KeyError" in result.root_cause or "key" in result.root_cause.lower()


# ===========================================================================
# B. IMPACT ANALYSIS TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# 7. Import tests
# ---------------------------------------------------------------------------


def test_impact_agent_can_be_imported():
    assert ImpactAgent is not None


def test_impact_context_can_be_imported():
    assert ImpactContext is not None


def test_impact_result_can_be_imported():
    assert ImpactResult is not None


def test_component_relationship_can_be_imported():
    assert ComponentRelationship is not None


# ---------------------------------------------------------------------------
# 8. Impact with supplied relationships
# ---------------------------------------------------------------------------


def test_impact_returns_result():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    assert isinstance(result, ImpactResult)


def test_changed_component_in_result():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    assert result.changed_component == "UserService"


def test_direct_dependants_identified():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    direct_names = {c.name for c in result.directly_affected}
    assert "AuthController" in direct_names
    assert "OrderService" in direct_names


def test_direct_dependants_confidence_confirmed():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    for comp in result.directly_affected:
        assert comp.confidence == ConfidenceLevel.CONFIRMED
        assert comp.impact_kind == "direct"


def test_indirect_dependants_identified():
    """AdminPanel → AuthController → UserService: AdminPanel is indirect."""
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    indirect_names = {c.name for c in result.indirectly_affected}
    assert "AdminPanel" in indirect_names


def test_indirect_dependants_confidence_inferred():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    for comp in result.indirectly_affected:
        assert comp.confidence == ConfidenceLevel.INFERRED
        assert comp.impact_kind == "indirect"


def test_direct_not_in_indirect():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    direct_names = {c.name for c in result.directly_affected}
    indirect_names = {c.name for c in result.indirectly_affected}
    # No component should be in both lists
    assert direct_names.isdisjoint(indirect_names)


def test_impact_summary_mentions_changed_component():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    assert "UserService" in result.impact_summary


def test_impact_confidence_confirmed_with_relationships():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# 9. Impact without relationships → UNKNOWN
# ---------------------------------------------------------------------------


def test_no_relationships_returns_unknown_confidence():
    agent = _make_impact_agent()
    ctx = ImpactContext(changed_component="UserService")
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_no_relationships_limitation_recorded():
    agent = _make_impact_agent()
    ctx = ImpactContext(changed_component="UserService")
    result = agent.analyse(ctx)
    found = any(
        "relationship" in lim.lower() or "dependency" in lim.lower()
        for lim in result.limitations
    )
    assert found


def test_no_relationships_unknown_in_summary():
    agent = _make_impact_agent()
    ctx = ImpactContext(changed_component="UserService")
    result = agent.analyse(ctx)
    assert "UNKNOWN" in result.impact_summary


def test_no_relationships_no_direct_affected():
    agent = _make_impact_agent()
    ctx = ImpactContext(changed_component="UserService")
    result = agent.analyse(ctx)
    assert result.directly_affected == []


def test_no_relationships_no_indirect_affected():
    agent = _make_impact_agent()
    ctx = ImpactContext(changed_component="UserService")
    result = agent.analyse(ctx)
    assert result.indirectly_affected == []


# ---------------------------------------------------------------------------
# 10. Related tests from supplied context
# ---------------------------------------------------------------------------


def test_related_tests_from_test_names():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        test_names=["test_create_user", "test_delete_user"],
    )
    result = agent.analyse(ctx)
    assert "test_create_user" in result.related_tests
    assert "test_delete_user" in result.related_tests


def test_related_tests_from_file_paths():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        test_file_paths=["tests/test_user_service.py"],
    )
    result = agent.analyse(ctx)
    assert "tests/test_user_service.py" in result.related_tests


def test_no_tests_limitation_recorded():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    found = any("test" in lim.lower() for lim in result.limitations)
    assert found


def test_tests_only_context_inferred_confidence():
    """With only tests and no relationships, confidence is INFERRED."""
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        test_names=["test_user_create"],
    )
    result = agent.analyse(ctx)
    # Tests supplied but no relationships → INFERRED
    assert result.confidence.level in (ConfidenceLevel.INFERRED, ConfidenceLevel.UNKNOWN)


# ---------------------------------------------------------------------------
# 11. No fabricated dependencies
# ---------------------------------------------------------------------------


def test_no_fabricated_direct_dependants():
    """Only components in the supplied relationships should appear."""
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=[
            ComponentRelationship(source="RealController", target="UserService"),
        ],
    )
    result = agent.analyse(ctx)
    direct_names = {c.name for c in result.directly_affected}
    assert "RealController" in direct_names
    assert "FakeController" not in direct_names
    assert "InventedService" not in direct_names


def test_no_fabricated_indirect_dependants():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=[
            ComponentRelationship(source="Controller", target="UserService"),
        ],
    )
    result = agent.analyse(ctx)
    indirect_names = {c.name for c in result.indirectly_affected}
    # No transitive deps were supplied beyond the one relationship
    assert "InventedTransitiveDep" not in indirect_names


def test_changed_component_not_in_affected():
    """The changed component itself should not appear in affected lists."""
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=[
            ComponentRelationship(source="UserService", target="DatabaseService"),
            ComponentRelationship(source="AuthController", target="UserService"),
        ],
    )
    result = agent.analyse(ctx)
    all_names = (
        {c.name for c in result.directly_affected}
        | {c.name for c in result.indirectly_affected}
    )
    assert "UserService" not in all_names


def test_no_git_evidence_in_impact():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


# ---------------------------------------------------------------------------
# 12. Evidence attribution
# ---------------------------------------------------------------------------


def test_source_code_evidence_for_changed_component():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.SOURCE_CODE in source_types


def test_file_evidence_for_relationships():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
    )
    result = agent.analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.FILE in source_types


def test_test_evidence_when_tests_supplied():
    agent = _make_impact_agent()
    ctx = ImpactContext(
        changed_component="UserService",
        relationships=_relationships(),
        test_names=["test_user"],
    )
    result = agent.analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.TEST in source_types
