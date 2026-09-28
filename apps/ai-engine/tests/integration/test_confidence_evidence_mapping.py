"""Contract-level integration tests: confidence and evidence mapping.

Category
--------
**Integration.** Real orchestrator + real output-validation pipeline + real
evidence models.  The LLM provider is the only substituted component, so
confidence is derived by production code paths, not by a test reimplementation.

Scope
-----
- whole-response confidence for a free-text answer is UNKNOWN
- evidence lists what was *available*, never what the model *claimed*
- source-code evidence appears when no chunks were supplied
- retrieved-chunk evidence appears when chunks were supplied
- evidence attribution (path, line range, chunk id) is preserved verbatim
- structured dependency output may be CONFIRMED, because it *is* grounded

Why it exists
-------------
Confidence is the engine's honesty mechanism, and its failure mode is silent
over-confidence: a plausible-looking answer graded CONFIRMED.  The rules below
are the engine's stated contract, asserted end-to-end through the orchestrator
so that a future change to the confidence rules cannot quietly relax them.
"""

from __future__ import annotations

import pytest

from app.evidence.models import ConfidenceLevel, EvidenceSourceType
from app.orchestrator import OrchestratorService
from tests.fixtures import (
    DEPENDENCY_CLAIM_TEXT,
    EXPLANATION_TEXT,
    EXTERNAL_CHUNK,
    INTERNAL_CHUNK,
    chunk_list,
    dependencies_input,
    explanation_input,
    static_provider,
    whitespace_content_provider,
)


async def _analyse(request, provider, chunks=None):
    service = OrchestratorService(provider=provider)
    return await service.analyse(request, chunks)


# ---------------------------------------------------------------------------
# Free-text responses are never CONFIRMED
# ---------------------------------------------------------------------------


async def test_free_text_answer_is_unknown_confidence():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.confidence is not None
    assert result.confidence.level is ConfidenceLevel.UNKNOWN


async def test_source_code_presence_does_not_upgrade_free_text_confidence():
    """Having the code is not the same as having verified the claims about it."""
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.confidence.evidence, "source code should still be recorded"
    assert result.confidence.level is not ConfidenceLevel.CONFIRMED


async def test_retrieved_chunks_do_not_upgrade_free_text_confidence():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    assert result.confidence.level is ConfidenceLevel.UNKNOWN


async def test_fabricated_git_claims_do_not_upgrade_confidence():
    """A confident-sounding answer about commits is still UNKNOWN.

    No Git history was supplied, so nothing about the commit is verified.
    """
    fabricated = (
        "This function was added in commit a1b2c3d by the platform team in "
        "PR #42 and is covered by three unit tests."
    )

    result = await _analyse(explanation_input(), static_provider(fabricated))

    assert result.confidence.level is ConfidenceLevel.UNKNOWN


async def test_degraded_output_stays_unknown():
    result = await _analyse(explanation_input(), whitespace_content_provider())

    assert result.confidence.level is ConfidenceLevel.UNKNOWN


async def test_confidence_notes_explain_the_unknown_determination():
    """A bare UNKNOWN with no explanation is not actionable for a caller."""
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.confidence.notes
    assert result.confidence.notes.strip()


# ---------------------------------------------------------------------------
# Evidence records availability, not correctness
# ---------------------------------------------------------------------------


async def test_source_code_evidence_is_recorded_without_chunks():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    source_types = [item.source_type for item in result.confidence.evidence]
    assert EvidenceSourceType.SOURCE_CODE in source_types


async def test_source_code_evidence_preserves_the_file_path():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    item = next(
        i
        for i in result.confidence.evidence
        if i.source_type is EvidenceSourceType.SOURCE_CODE
    )
    assert item.file_path == "src/math_ops.py"


async def test_retrieved_chunk_evidence_is_recorded_when_chunks_supplied():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    source_types = [item.source_type for item in result.confidence.evidence]
    assert EvidenceSourceType.RETRIEVED_CHUNK in source_types


async def test_chunk_evidence_preserves_attribution_verbatim():
    """Path, line range and chunk id must survive into the evidence item.

    This is the traceability requirement: a caller must be able to open exactly
    the chunk the engine claims to have used.
    """
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    item = next(
        i
        for i in result.confidence.evidence
        if i.source_type is EvidenceSourceType.RETRIEVED_CHUNK
    )
    assert item.chunk_id == INTERNAL_CHUNK.chunk_id
    assert item.file_path == INTERNAL_CHUNK.file_path
    assert item.line_start == INTERNAL_CHUNK.line_start
    assert item.line_end == INTERNAL_CHUNK.line_end


async def test_evidence_count_matches_the_number_of_chunks_supplied():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    chunk_items = [
        i
        for i in result.confidence.evidence
        if i.source_type is EvidenceSourceType.RETRIEVED_CHUNK
    ]
    assert len(chunk_items) == 2


async def test_no_git_commit_evidence_is_ever_fabricated():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    source_types = {item.source_type for item in result.confidence.evidence}
    assert EvidenceSourceType.GIT_COMMIT not in source_types


async def test_no_test_evidence_is_ever_fabricated():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    source_types = {item.source_type for item in result.confidence.evidence}
    assert EvidenceSourceType.TEST not in source_types


async def test_every_evidence_item_is_populated():
    """No evidence item may be emitted as a bare placeholder."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    for item in result.confidence.evidence:
        assert item.source_type is not None
        assert item.description and item.description.strip()


# ---------------------------------------------------------------------------
# Structured output may be CONFIRMED, because it is genuinely grounded
# ---------------------------------------------------------------------------


async def test_grounded_dependencies_are_produced_with_unknown_response_confidence():
    """Two distinct claims with two distinct confidence levels.

    The summary is free text, so the *response* is UNKNOWN.  The dependency
    list, however, is extracted from the AST, so each entry is directly
    established by the supplied source.
    """
    result = await _analyse(
        dependencies_input(),
        static_provider(DEPENDENCY_CLAIM_TEXT),
    )

    assert result.confidence.level is ConfidenceLevel.UNKNOWN
    assert result.dependencies is not None
    assert [d.name for d in result.dependencies.dependencies] == ["math", "pathlib"]


async def test_dependency_response_is_deterministic_across_providers():
    """The structured output must not depend on what the model said."""
    first = await _analyse(dependencies_input(), static_provider("One answer."))
    second = await _analyse(dependencies_input(), static_provider("A different answer."))

    assert [d.name for d in first.dependencies.dependencies] == [
        d.name for d in second.dependencies.dependencies
    ]


@pytest.mark.parametrize("provider_text", ["", "   ", "Nothing to report."])
async def test_dependency_grounding_survives_any_provider_output(provider_text):
    result = await _analyse(dependencies_input(), static_provider(provider_text))

    assert [d.name for d in result.dependencies.dependencies] == ["math", "pathlib"]
