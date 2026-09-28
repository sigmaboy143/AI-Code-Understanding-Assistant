"""Deterministic AI evaluation of the AI Engine's output quality.

Category
--------
**Evaluation.** These tests do not check that the code runs — the integration
suite does that.  They check that the answers are *trustworthy*: non-empty,
grounded in what was actually supplied, honest about uncertainty, and
traceable back to a source.

Method
------
Each check is a small, named invariant that a reviewer can read and agree or
disagree with, rather than an opaque numeric score.  A numeric score would be
uninterpretable and would drift silently; a violated invariant names exactly
which guarantee broke.

Expectations are imported from ``tests.fixtures.expected_outputs`` rather than
written inline.  That separation is deliberate: the expectations were authored
from the *specification* ("free-text claims are not claim-mapped to evidence",
"dependencies come only from real imports"), not from reading the
implementation, so a test comparing the two is a real check.

No test in this package requires a live LLM
--------------------------------------------
The provider is a deterministic fixture, so the suite runs in well under a
second and gives the same result on every machine.  The trade-off is explicit:
these tests evaluate the engine's *grounding, confidence, and traceability
logic*, not the prose quality of ``qwen3:8b``.  Evaluating model prose requires
a live model, is not reproducible, and therefore cannot gate a commit.

Invariants evaluated
--------------------
1. The explanation is non-empty and usable.
2. Unsupported repository facts are never promoted into structured output.
3. Dependency output is grounded in a real import statement.
4. Confidence is UNKNOWN when evidence is insufficient.
5. Confidence is CONFIRMED or INFERRED only where genuinely grounded.
6. Evidence fields remain traceable to the input that produced them.
7. Grounded output is invariant to what the model happened to say.
"""

from __future__ import annotations

import pytest

from app.orchestrator import OrchestratorService
from tests.fixtures import (
    ALL_ANALYSES,
    CONFIDENCE_LEVELS,
    DEPENDENCIES_SOURCE,
    DEPENDENCY_CLAIM_TEXT,
    ERROR_EXPLANATION_TEXT,
    EXPLANATION_TEXT,
    EXPECTED_CONFIRMED_LEVEL,
    EXPECTED_GROUNDED_DEPENDENCIES,
    EXPECTED_INFERRED_LEVEL,
    EXPECTED_UNKNOWN_LEVEL,
    EXPECTED_UNGROUNDED_DEPENDENCIES,
    EXTERNAL_CHUNK,
    FABRICATED_REPOSITORY_FACTS,
    GIT_FACT_CLAIM_TEXT,
    IMPROVEMENT_TEXT,
    INTERNAL_CHUNK,
    PRODUCIBLE_EVIDENCE_SOURCE_TYPES,
    RESERVED_EVIDENCE_SOURCE_TYPES,
    SIMPLE_FILE_PATH,
    STRUCTURE_TEXT,
    chunk_list,
    dependencies_input,
    error_explanation_input,
    explanation_input,
    improvements_input,
    static_provider,
    structure_input,
    whitespace_content_provider,
)

#: Provider outputs that are not usable answers.  The engine must still return
#: a non-empty summary rather than an empty string or a crash.
NON_ANSWERS = ("", "   ", "\n\t\n", "I don't know.", "N/A")


async def _analyse(request, provider, chunks=None):
    """Run a request through the real orchestrator with a fixed provider."""
    service = OrchestratorService(provider=provider)
    return await service.analyse(request, chunks)


# ---------------------------------------------------------------------------
# Invariant 1 — the answer is usable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", NON_ANSWERS)
async def test_summary_is_never_empty(text):
    """A blank summary is a failed analysis, however the model phrased it."""
    result = await _analyse(explanation_input(), static_provider(text))

    assert result.summary.strip(), f"empty summary for provider text {text!r}"


async def test_usable_answer_reaches_the_consumer_unchanged():
    """Normalisation must not mangle an answer that is already good."""
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.summary == EXPLANATION_TEXT


@pytest.mark.parametrize(
    ("build", "text"),
    [
        (structure_input, STRUCTURE_TEXT),
        (error_explanation_input, ERROR_EXPLANATION_TEXT),
        (improvements_input, IMPROVEMENT_TEXT),
        (explanation_input, EXPLANATION_TEXT),
        (dependencies_input, EXPLANATION_TEXT),
    ],
    ids=["structure", "error", "improvements", "explanation", "dependencies"],
)
async def test_every_analysis_intent_produces_a_summary(build, text):
    """All five intents are exercised, so none may be a dead end."""
    result = await _analyse(build(), static_provider(text))

    assert result.summary.strip()


async def test_summary_is_bounded_in_length():
    """An unbounded summary is a denial-of-service vector for the caller."""
    result = await _analyse(explanation_input(), static_provider("word " * 50_000))

    assert len(result.summary) <= 10_000 + len(" [truncated]")


# ---------------------------------------------------------------------------
# Invariant 2 — unsupported repository facts are never promoted
# ---------------------------------------------------------------------------


async def test_fabricated_git_facts_never_reach_structured_output():
    """Commit hashes, PR numbers and test counts are absent from the input.

    The model may say them out loud; the engine must never make them structural.
    """
    result = await _analyse(explanation_input(), static_provider(GIT_FACT_CLAIM_TEXT))

    assert result.structure is None
    assert result.dependencies is None
    assert result.improvements == []


async def test_fabricated_git_facts_never_reach_evidence_items():
    """Evidence must point at supplied material, never at a claimed commit."""
    result = await _analyse(
        explanation_input(),
        static_provider(GIT_FACT_CLAIM_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    rendered = " ".join(
        f"{item.description} {item.file_path} {item.chunk_id}"
        for item in result.confidence.evidence
    )
    for fact in FABRICATED_REPOSITORY_FACTS:
        assert fact not in rendered


@pytest.mark.parametrize("reserved", RESERVED_EVIDENCE_SOURCE_TYPES)
async def test_reserved_evidence_types_are_never_invented(reserved):
    """`test` and `git_commit` exist in the contract but must stay unused here."""
    result = await _analyse(
        explanation_input(),
        static_provider(GIT_FACT_CLAIM_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    assert reserved not in {item.source_type for item in result.confidence.evidence}


async def test_evidence_source_types_are_within_the_producible_set():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    assert {i.source_type for i in result.confidence.evidence}.issubset(
        set(PRODUCIBLE_EVIDENCE_SOURCE_TYPES)
    )


async def test_no_impact_analysis_is_invented():
    """Nothing in the input supports an impact claim, so none may appear."""
    result = await _analyse(
        dependencies_input(),
        static_provider("Changing this breaks the billing service."),
    )

    assert result.dependencies is not None
    assert result.dependencies.impacts == []


# ---------------------------------------------------------------------------
# Invariant 3 — dependency output is grounded
# ---------------------------------------------------------------------------


async def test_dependencies_match_the_hand_written_expectation():
    result = await _analyse(dependencies_input(), static_provider(EXPLANATION_TEXT))

    assert [(d.name, d.kind.value) for d in result.dependencies.dependencies] == list(
        EXPECTED_GROUNDED_DEPENDENCIES
    )


@pytest.mark.parametrize("hallucinated", EXPECTED_UNGROUNDED_DEPENDENCIES)
async def test_unimported_library_is_never_returned(hallucinated):
    """Grounding is AST-based, so an unimported name cannot appear."""
    result = await _analyse(
        dependencies_input(),
        static_provider(f"This code uses {hallucinated}."),
    )

    assert hallucinated not in [d.name for d in result.dependencies.dependencies]


async def test_textual_dependency_claim_is_not_structured():
    result = await _analyse(dependencies_input(), static_provider(DEPENDENCY_CLAIM_TEXT))

    assert "requests" not in [d.name for d in result.dependencies.dependencies]


# ---------------------------------------------------------------------------
# Invariant 4 — confidence is UNKNOWN when evidence is insufficient
# ---------------------------------------------------------------------------


async def test_confidence_is_unknown_without_retrieved_evidence():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.confidence.level is EXPECTED_UNKNOWN_LEVEL


async def test_confidence_is_unknown_when_the_model_says_nothing_useful():
    result = await _analyse(explanation_input(), whitespace_content_provider())

    assert result.confidence.level is EXPECTED_UNKNOWN_LEVEL


async def test_confidence_is_unknown_even_with_rich_retrieved_evidence():
    """Plenty of context is still not verification of the model's claims."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    assert result.confidence.level is EXPECTED_UNKNOWN_LEVEL


async def test_unknown_confidence_still_records_what_was_available():
    """UNKNOWN must be explicable, not silent."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    assert result.confidence.evidence
    assert result.confidence.notes and result.confidence.notes.strip()


# ---------------------------------------------------------------------------
# Invariant 5 — CONFIRMED / INFERRED only where genuinely grounded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overclaimed",
    [EXPECTED_CONFIRMED_LEVEL, EXPECTED_INFERRED_LEVEL],
    ids=["confirmed", "inferred"],
)
async def test_no_free_text_path_ever_overclaims(overclaimed):
    """Guards the entire free-text surface at once.

    Every analysis intent goes through the same validation pipeline, so holding
    for all of them means no future intent can introduce an over-confident path.
    """
    builders = (
        explanation_input,
        structure_input,
        error_explanation_input,
        improvements_input,
        dependencies_input,
    )

    for build in builders:
        result = await _analyse(build(), static_provider(EXPLANATION_TEXT))

        assert result.confidence.level is not overclaimed, (
            f"{build.__name__} produced {result.confidence.level}"
        )


async def test_confidence_level_is_always_one_of_the_three_states():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert result.confidence.level in set(CONFIDENCE_LEVELS)


async def test_confidence_vocabulary_is_exactly_three_states():
    """A new level would break every consumer's exhaustive switch."""
    assert len(set(CONFIDENCE_LEVELS)) == 3


# ---------------------------------------------------------------------------
# Invariant 6 — evidence stays traceable
# ---------------------------------------------------------------------------


async def test_evidence_points_at_the_submitted_file():
    result = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    item = next(i for i in result.confidence.evidence if i.file_path is not None)
    assert item.file_path == SIMPLE_FILE_PATH


async def test_chunk_evidence_points_at_the_exact_chunk_used():
    """Path, chunk id and line range must survive verbatim."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    item = next(i for i in result.confidence.evidence if i.chunk_id is not None)
    assert item.chunk_id == INTERNAL_CHUNK.chunk_id
    assert item.file_path == INTERNAL_CHUNK.file_path
    assert item.line_start == INTERNAL_CHUNK.line_start
    assert item.line_end == INTERNAL_CHUNK.line_end


async def test_evidence_only_references_supplied_material():
    """Every evidence path must be one the caller actually supplied."""
    supplied = {SIMPLE_FILE_PATH, INTERNAL_CHUNK.file_path, EXTERNAL_CHUNK.file_path}

    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    referenced = {i.file_path for i in result.confidence.evidence if i.file_path}
    assert referenced
    assert referenced.issubset(supplied)


async def test_every_evidence_item_is_human_readable():
    """An evidence item with no description is not traceable in practice."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    for item in result.confidence.evidence:
        assert item.description and item.description.strip()


async def test_line_numbers_are_one_based_when_present():
    """A 0-based line number would send a reader to the wrong line."""
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    for item in result.confidence.evidence:
        if item.line_start is not None:
            assert item.line_start >= 1
        if item.line_end is not None:
            assert item.line_end >= 1


async def test_evidence_never_references_a_git_object():
    result = await _analyse(
        explanation_input(),
        static_provider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    for item in result.confidence.evidence:
        assert "commit" not in (item.description or "").lower()


# ---------------------------------------------------------------------------
# Invariant 7 — grounded output is reproducible
# ---------------------------------------------------------------------------


async def test_structured_output_is_identical_across_contradictory_answers():
    """Structured fields come from the code, not from the prose."""
    quiet = await _analyse(dependencies_input(), static_provider("No comment."))
    loud = await _analyse(
        dependencies_input(),
        static_provider(
            "Uses math, pathlib, requests, numpy, torch, flask, pandas and "
            "asyncio, all imported at the top of the file."
        ),
    )

    assert [d.name for d in quiet.dependencies.dependencies] == [
        d.name for d in loud.dependencies.dependencies
    ]


async def test_repeated_identical_requests_produce_identical_results():
    first = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))
    second = await _analyse(explanation_input(), static_provider(EXPLANATION_TEXT))

    assert first.summary == second.summary
    assert first.confidence.model_dump() == second.confidence.model_dump()
    assert first.metadata.model_dump() == second.metadata.model_dump()


async def test_grounded_dependencies_survive_a_blank_completion():
    """A blank completion must not erase the grounded dependency list."""
    result = await _analyse(dependencies_input(), static_provider(""))

    assert [d.name for d in result.dependencies.dependencies] == [
        name for name, _kind in EXPECTED_GROUNDED_DEPENDENCIES
    ]


async def test_dependency_extraction_is_stable_across_repeats():
    """Re-running must not accumulate or drop entries."""
    results = [
        await _analyse(
            dependencies_input(source_code=DEPENDENCIES_SOURCE),
            static_provider(EXPLANATION_TEXT),
        )
        for _ in range(3)
    ]

    name_lists = [[d.name for d in r.dependencies.dependencies] for r in results]
    assert name_lists[0] == name_lists[1] == name_lists[2]
    assert len(name_lists[0]) == len(set(name_lists[0])), "duplicate dependencies"


async def test_every_analysis_intent_returns_metadata_for_the_request():
    """Metadata is how a caller knows what was actually analysed."""
    for analysis in ALL_ANALYSES:
        result = await _analyse(
            explanation_input(analyses=[analysis]),
            static_provider(EXPLANATION_TEXT),
        )

        assert result.metadata.analyses == [analysis]
