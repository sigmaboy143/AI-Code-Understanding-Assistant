"""Tests for the context builder (Task 8).

Coverage
--------
- Context creation from a valid request
- Context ordering (chunks sorted by descending relevance)
- Retrieval chunk inclusion and attribution preservation
- Duplicate chunk elimination (by chunk_id)
- Size / character limit behavior
- Empty retrieval (no chunks provided)
- Question and user context inclusion
- Deterministic output (same input → same output)
- Language, file_path, and analyses forwarded correctly
- truncated flag behavior
- IncludedChunk attribution fields preserved
"""

from __future__ import annotations

import pytest

from app.context_builder import ContextBuilder, BuiltContext, MAX_CONTEXT_CHARS
from app.context_builder.builder import IncludedChunk, _deduplicate_chunks
from app.retrieval.base import RetrievedChunk
from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest, ProgrammingLanguage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CODE = "def add(a, b):\n    return a + b\n"


def _make_request(**overrides) -> CodeUnderstandingRequest:
    base = {
        "source_code": SAMPLE_CODE,
        "language": "python",
        "analyses": [AnalysisType.EXPLANATION],
    }
    base.update(overrides)
    return CodeUnderstandingRequest(**base)


def _chunk(
    chunk_id: str,
    content: str,
    file_path: str = "src/code.py",
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    source_type: str = "source_code",
    relevance_score: float = 0.5,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        symbol=symbol,
        content=content,
        line_start=line_start,
        line_end=line_end,
        source_type=source_type,
        relevance_score=relevance_score,
    )


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


def test_context_builder_can_be_instantiated():
    builder = ContextBuilder()
    assert builder is not None


def test_context_builder_rejects_zero_max_chars():
    with pytest.raises(ValueError):
        ContextBuilder(max_chars=0)


def test_context_builder_rejects_negative_max_chars():
    with pytest.raises(ValueError):
        ContextBuilder(max_chars=-1)


def test_build_returns_built_context():
    builder = ContextBuilder()
    ctx = builder.build(_make_request())
    assert isinstance(ctx, BuiltContext)


# ---------------------------------------------------------------------------
# Mandatory fields always present
# ---------------------------------------------------------------------------


def test_context_contains_source_code():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.source_code == SAMPLE_CODE


def test_context_contains_language():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.language is ProgrammingLanguage.PYTHON


def test_context_contains_analyses():
    analyses = [AnalysisType.EXPLANATION, AnalysisType.STRUCTURE]
    ctx = ContextBuilder().build(_make_request(analyses=analyses))
    assert set(ctx.analyses) == set(analyses)


# ---------------------------------------------------------------------------
# Optional fields: question and user context
# ---------------------------------------------------------------------------


def test_context_includes_question_when_present():
    ctx = ContextBuilder().build(_make_request(question="What does add do?"))
    assert ctx.question == "What does add do?"


def test_context_question_is_none_when_absent():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.question is None


def test_context_includes_user_context_when_present():
    ctx = ContextBuilder().build(_make_request(context="Error on line 1."))
    assert ctx.user_context == "Error on line 1."


def test_context_user_context_is_none_when_absent():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.user_context is None


def test_context_includes_file_path_when_present():
    ctx = ContextBuilder().build(_make_request(file_path="src/math.py"))
    assert ctx.file_path == "src/math.py"


def test_context_file_path_is_none_when_absent():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.file_path is None


# ---------------------------------------------------------------------------
# Empty retrieval
# ---------------------------------------------------------------------------


def test_no_chunks_produces_empty_included_list():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.included_chunks == []


def test_none_chunks_produces_empty_included_list():
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=None)
    assert ctx.included_chunks == []


def test_empty_list_chunks_produces_empty_included_list():
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[])
    assert ctx.included_chunks == []


def test_no_chunks_produces_not_truncated():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.truncated is False


# ---------------------------------------------------------------------------
# Chunk inclusion and attribution preservation
# ---------------------------------------------------------------------------


def test_single_chunk_included():
    chunk = _chunk("c1", "def login(): pass", file_path="auth.py", relevance_score=0.8)
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert len(ctx.included_chunks) == 1


def test_chunk_attribution_chunk_id_preserved():
    chunk = _chunk("my-chunk-id", "some content")
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].chunk_id == "my-chunk-id"


def test_chunk_attribution_file_path_preserved():
    chunk = _chunk("c1", "content", file_path="app/service.py")
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].file_path == "app/service.py"


def test_chunk_attribution_symbol_preserved():
    chunk = _chunk("c1", "content", symbol="MyClass.method")
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].symbol == "MyClass.method"


def test_chunk_attribution_line_range_preserved():
    chunk = _chunk("c1", "content", line_start=10, line_end=20)
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].line_start == 10
    assert ctx.included_chunks[0].line_end == 20


def test_chunk_attribution_source_type_preserved():
    chunk = _chunk("c1", "content", source_type="docstring")
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].source_type == "docstring"


def test_chunk_attribution_relevance_score_preserved():
    chunk = _chunk("c1", "content", relevance_score=0.77)
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert ctx.included_chunks[0].relevance_score == pytest.approx(0.77)


def test_included_chunk_is_included_chunk_type():
    chunk = _chunk("c1", "content")
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=[chunk])
    assert isinstance(ctx.included_chunks[0], IncludedChunk)


# ---------------------------------------------------------------------------
# Ordering — chunks sorted by descending relevance
# ---------------------------------------------------------------------------


def test_chunks_ordered_by_descending_relevance():
    chunks = [
        _chunk("low", "low relevance content", relevance_score=0.2),
        _chunk("high", "high relevance content", relevance_score=0.9),
        _chunk("mid", "medium relevance content", relevance_score=0.5),
    ]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    scores = [c.relevance_score for c in ctx.included_chunks]
    assert scores == sorted(scores, reverse=True)


def test_highest_relevance_chunk_is_first():
    chunks = [
        _chunk("a", "aaa content", relevance_score=0.1),
        _chunk("b", "bbb content", relevance_score=0.95),
    ]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    assert ctx.included_chunks[0].chunk_id == "b"


# ---------------------------------------------------------------------------
# Duplicate elimination
# ---------------------------------------------------------------------------


def test_duplicate_chunk_ids_are_deduplicated():
    chunks = [
        _chunk("dup", "first version", relevance_score=0.8),
        _chunk("dup", "second version", relevance_score=0.9),  # same chunk_id
    ]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    assert len(ctx.included_chunks) == 1


def test_first_occurrence_wins_on_deduplication():
    """When the same chunk_id appears twice, the first occurrence is kept."""
    chunks = [
        _chunk("dup", "first version", relevance_score=0.4),
        _chunk("dup", "second version", relevance_score=0.9),
    ]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    assert ctx.included_chunks[0].content == "first version"


def test_deduplicate_chunks_helper_preserves_unique():
    chunks = [_chunk("a", "x"), _chunk("b", "y"), _chunk("c", "z")]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 3


def test_deduplicate_chunks_helper_removes_duplicate():
    chunks = [_chunk("a", "x"), _chunk("a", "x again")]
    result = _deduplicate_chunks(chunks)
    assert len(result) == 1


def test_no_duplicate_content_in_output_for_identical_ids():
    chunks = [
        _chunk("same", "content A", relevance_score=0.5),
        _chunk("same", "content A", relevance_score=0.5),
    ]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    ids = [c.chunk_id for c in ctx.included_chunks]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Size / limit behavior
# ---------------------------------------------------------------------------


def test_context_builder_respects_max_chars_limit():
    """Chunks that push total past max_chars are dropped."""
    # Source code is ~30 chars; budget is 50 total.
    tiny_code = "x = 1"  # 5 chars
    request = _make_request(source_code=tiny_code)
    # Each chunk is 20 chars; budget after source is 45 chars.
    # With max_chars=30 only 1 chunk can fit (20 chars) after 5-char code.
    chunks = [
        _chunk("a", "a" * 20, relevance_score=0.9),
        _chunk("b", "b" * 20, relevance_score=0.8),
    ]
    ctx = ContextBuilder(max_chars=30).build(request, retrieved_chunks=chunks)
    # The high-relevance chunk 'a' fits (5+20=25 ≤ 30), 'b' does not.
    assert len(ctx.included_chunks) == 1
    assert ctx.included_chunks[0].chunk_id == "a"


def test_truncated_flag_set_when_chunk_dropped():
    tiny_code = "x = 1"  # 5 chars
    request = _make_request(source_code=tiny_code)
    chunks = [
        _chunk("a", "a" * 20, relevance_score=0.9),
        _chunk("b", "b" * 20, relevance_score=0.8),
    ]
    ctx = ContextBuilder(max_chars=30).build(request, retrieved_chunks=chunks)
    assert ctx.truncated is True


def test_truncated_flag_false_when_all_fit():
    request = _make_request(source_code="x = 1")
    chunks = [_chunk("a", "small", relevance_score=0.9)]
    ctx = ContextBuilder(max_chars=MAX_CONTEXT_CHARS).build(request, retrieved_chunks=chunks)
    assert ctx.truncated is False


def test_high_relevance_chunk_preferred_over_low_when_budget_tight():
    """Higher relevance chunks should survive when budget is tight."""
    tiny_code = "x = 1"  # 5 chars
    request = _make_request(source_code=tiny_code)
    chunks = [
        _chunk("low", "l" * 20, relevance_score=0.1),
        _chunk("high", "h" * 20, relevance_score=0.9),
    ]
    ctx = ContextBuilder(max_chars=30).build(request, retrieved_chunks=chunks)
    included_ids = {c.chunk_id for c in ctx.included_chunks}
    assert "high" in included_ids


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


def test_same_input_produces_same_output():
    chunks = [
        _chunk("a", "content alpha", relevance_score=0.7),
        _chunk("b", "content beta", relevance_score=0.4),
    ]
    builder = ContextBuilder()
    ctx1 = builder.build(_make_request(), retrieved_chunks=chunks)
    ctx2 = builder.build(_make_request(), retrieved_chunks=chunks)
    assert [c.chunk_id for c in ctx1.included_chunks] == [c.chunk_id for c in ctx2.included_chunks]


def test_deterministic_ordering_on_equal_relevance():
    """Equal-relevance chunks must be ordered the same every call."""
    chunks = [
        _chunk("a", "same score", relevance_score=0.5),
        _chunk("b", "same score", relevance_score=0.5),
    ]
    builder = ContextBuilder()
    ctx1 = builder.build(_make_request(), retrieved_chunks=chunks)
    ctx2 = builder.build(_make_request(), retrieved_chunks=chunks)
    assert [c.chunk_id for c in ctx1.included_chunks] == [c.chunk_id for c in ctx2.included_chunks]


# ---------------------------------------------------------------------------
# Extra sections reserved
# ---------------------------------------------------------------------------


def test_extra_sections_is_empty_by_default():
    ctx = ContextBuilder().build(_make_request())
    assert ctx.extra_sections == {}


# ---------------------------------------------------------------------------
# Multiple chunks all included when budget allows
# ---------------------------------------------------------------------------


def test_multiple_chunks_all_included_when_budget_sufficient():
    chunks = [_chunk(str(i), f"content_{i}", relevance_score=float(i) / 10) for i in range(1, 4)]
    ctx = ContextBuilder().build(_make_request(), retrieved_chunks=chunks)
    assert len(ctx.included_chunks) == 3
