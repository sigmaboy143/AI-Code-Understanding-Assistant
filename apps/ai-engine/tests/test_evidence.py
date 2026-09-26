"""Tests for the evidence and confidence system (Task 9).

Coverage
--------
- EvidenceSourceType enum validation
- ConfidenceLevel enum: CONFIRMED, INFERRED, UNKNOWN
- EvidenceItem model: required fields, optional fields, validation
- ResponseConfidence model: default is UNKNOWN, evidence list, notes
- ResponseConfidence.unknown() constructor
- ResponseConfidence.from_chunks() — CONFIRMED when chunks present
- ResponseConfidence.from_chunks() — UNKNOWN when no chunks
- ResponseConfidence.from_source_code()
- Source metadata (file_path, line_start, line_end, chunk_id) preserved
- Missing evidence → UNKNOWN behavior
- No fabricated evidence in any constructor
- EvidenceItem rejects invalid line numbers
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evidence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    ResponseConfidence,
)
from app.context_builder.builder import IncludedChunk


# ---------------------------------------------------------------------------
# EvidenceSourceType
# ---------------------------------------------------------------------------


def test_evidence_source_type_values_exist():
    assert EvidenceSourceType.SOURCE_CODE == "source_code"
    assert EvidenceSourceType.RETRIEVED_CHUNK == "retrieved_chunk"
    assert EvidenceSourceType.FILE == "file"
    assert EvidenceSourceType.DOCUMENTATION == "documentation"
    assert EvidenceSourceType.TEST == "test"
    assert EvidenceSourceType.GIT_COMMIT == "git_commit"


def test_evidence_source_type_is_string_enum():
    assert isinstance(EvidenceSourceType.SOURCE_CODE, str)


# ---------------------------------------------------------------------------
# ConfidenceLevel
# ---------------------------------------------------------------------------


def test_confidence_level_confirmed():
    assert ConfidenceLevel.CONFIRMED == "CONFIRMED"


def test_confidence_level_inferred():
    assert ConfidenceLevel.INFERRED == "INFERRED"


def test_confidence_level_unknown():
    assert ConfidenceLevel.UNKNOWN == "UNKNOWN"


def test_confidence_level_is_string_enum():
    assert isinstance(ConfidenceLevel.CONFIRMED, str)


def test_confidence_level_has_exactly_three_values():
    assert len(list(ConfidenceLevel)) == 3


# ---------------------------------------------------------------------------
# EvidenceItem — valid construction
# ---------------------------------------------------------------------------


def test_evidence_item_requires_source_type():
    with pytest.raises(ValidationError):
        EvidenceItem()  # type: ignore[call-arg]


def test_evidence_item_minimal():
    item = EvidenceItem(source_type=EvidenceSourceType.SOURCE_CODE)
    assert item.source_type is EvidenceSourceType.SOURCE_CODE
    assert item.file_path is None
    assert item.line_start is None
    assert item.line_end is None
    assert item.chunk_id is None
    assert item.description is None


def test_evidence_item_full():
    item = EvidenceItem(
        source_type=EvidenceSourceType.RETRIEVED_CHUNK,
        file_path="src/auth.py",
        line_start=10,
        line_end=25,
        chunk_id="chunk-abc",
        description="Auth.login definition",
    )
    assert item.file_path == "src/auth.py"
    assert item.line_start == 10
    assert item.line_end == 25
    assert item.chunk_id == "chunk-abc"
    assert item.description == "Auth.login definition"


def test_evidence_item_file_evidence():
    item = EvidenceItem(source_type=EvidenceSourceType.FILE, file_path="src/main.py")
    assert item.source_type is EvidenceSourceType.FILE
    assert item.file_path == "src/main.py"


def test_evidence_item_documentation_evidence():
    item = EvidenceItem(
        source_type=EvidenceSourceType.DOCUMENTATION,
        description="Module docstring",
    )
    assert item.source_type is EvidenceSourceType.DOCUMENTATION


# ---------------------------------------------------------------------------
# EvidenceItem — validation
# ---------------------------------------------------------------------------


def test_evidence_item_rejects_zero_line_start():
    with pytest.raises(ValidationError):
        EvidenceItem(source_type=EvidenceSourceType.SOURCE_CODE, line_start=0)


def test_evidence_item_rejects_negative_line_start():
    with pytest.raises(ValidationError):
        EvidenceItem(source_type=EvidenceSourceType.SOURCE_CODE, line_start=-5)


def test_evidence_item_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EvidenceItem(
            source_type=EvidenceSourceType.SOURCE_CODE,
            unexpected_field="bad",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# ResponseConfidence — default is UNKNOWN
# ---------------------------------------------------------------------------


def test_response_confidence_default_is_unknown():
    rc = ResponseConfidence()
    assert rc.level is ConfidenceLevel.UNKNOWN


def test_response_confidence_default_evidence_is_empty():
    rc = ResponseConfidence()
    assert rc.evidence == []


def test_response_confidence_default_notes_is_none():
    rc = ResponseConfidence()
    assert rc.notes is None


def test_response_confidence_unknown_factory():
    rc = ResponseConfidence.unknown()
    assert rc.level is ConfidenceLevel.UNKNOWN
    assert rc.evidence == []


def test_response_confidence_unknown_factory_with_notes():
    rc = ResponseConfidence.unknown(notes="No evidence available.")
    assert rc.notes == "No evidence available."


# ---------------------------------------------------------------------------
# ResponseConfidence — from_chunks
# ---------------------------------------------------------------------------


def _make_included_chunk(chunk_id: str, file_path: str = "src/x.py") -> IncludedChunk:
    return IncludedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        content="def foo(): pass",
        relevance_score=0.8,
    )


def test_from_chunks_empty_list_gives_unknown():
    rc = ResponseConfidence.from_chunks([])
    assert rc.level is ConfidenceLevel.UNKNOWN


def test_from_chunks_with_chunks_gives_confirmed():
    chunks = [_make_included_chunk("c1")]
    rc = ResponseConfidence.from_chunks(chunks)
    assert rc.level is ConfidenceLevel.CONFIRMED


def test_from_chunks_evidence_count_matches_chunks():
    chunks = [_make_included_chunk("c1"), _make_included_chunk("c2")]
    rc = ResponseConfidence.from_chunks(chunks)
    assert len(rc.evidence) == 2


def test_from_chunks_evidence_source_type_is_retrieved_chunk():
    chunks = [_make_included_chunk("c1")]
    rc = ResponseConfidence.from_chunks(chunks)
    assert rc.evidence[0].source_type is EvidenceSourceType.RETRIEVED_CHUNK


def test_from_chunks_evidence_preserves_file_path():
    chunks = [_make_included_chunk("c1", file_path="app/auth.py")]
    rc = ResponseConfidence.from_chunks(chunks)
    assert rc.evidence[0].file_path == "app/auth.py"


def test_from_chunks_evidence_preserves_chunk_id():
    chunks = [_make_included_chunk("my-chunk-id")]
    rc = ResponseConfidence.from_chunks(chunks)
    assert rc.evidence[0].chunk_id == "my-chunk-id"


def test_from_chunks_preserves_line_range():
    chunk = IncludedChunk(
        chunk_id="c1",
        file_path="src/foo.py",
        content="code",
        line_start=5,
        line_end=15,
        relevance_score=0.7,
    )
    rc = ResponseConfidence.from_chunks([chunk])
    assert rc.evidence[0].line_start == 5
    assert rc.evidence[0].line_end == 15


def test_from_chunks_no_fabricated_evidence():
    """from_chunks must not invent evidence not present in the supplied chunks."""
    chunks = [_make_included_chunk("real-chunk")]
    rc = ResponseConfidence.from_chunks(chunks)
    # Evidence must only reference the supplied chunk
    assert all(e.chunk_id == "real-chunk" for e in rc.evidence)


def test_from_chunks_with_notes():
    rc = ResponseConfidence.from_chunks(
        [_make_included_chunk("c1")], notes="Derived from RAG."
    )
    assert rc.notes == "Derived from RAG."


# ---------------------------------------------------------------------------
# ResponseConfidence — from_source_code
# ---------------------------------------------------------------------------


def test_from_source_code_gives_confirmed():
    rc = ResponseConfidence.from_source_code("src/main.py")
    assert rc.level is ConfidenceLevel.CONFIRMED


def test_from_source_code_evidence_source_type():
    rc = ResponseConfidence.from_source_code("src/main.py")
    assert rc.evidence[0].source_type is EvidenceSourceType.SOURCE_CODE


def test_from_source_code_preserves_file_path():
    rc = ResponseConfidence.from_source_code("my/file.py")
    assert rc.evidence[0].file_path == "my/file.py"


def test_from_source_code_with_none_file_path():
    rc = ResponseConfidence.from_source_code(None)
    assert rc.level is ConfidenceLevel.CONFIRMED
    assert rc.evidence[0].file_path is None


def test_from_source_code_with_notes():
    rc = ResponseConfidence.from_source_code("f.py", notes="From submitted code.")
    assert rc.notes == "From submitted code."


# ---------------------------------------------------------------------------
# Missing evidence → UNKNOWN
# ---------------------------------------------------------------------------


def test_unknown_when_explicitly_created():
    rc = ResponseConfidence(level=ConfidenceLevel.UNKNOWN, evidence=[])
    assert rc.level is ConfidenceLevel.UNKNOWN
    assert rc.evidence == []


def test_inferred_confidence_can_be_created_without_evidence():
    """INFERRED is a valid state — represents reasoned conclusions."""
    rc = ResponseConfidence(level=ConfidenceLevel.INFERRED, evidence=[])
    assert rc.level is ConfidenceLevel.INFERRED


def test_confirmed_confidence_can_carry_evidence():
    evidence = [EvidenceItem(source_type=EvidenceSourceType.SOURCE_CODE)]
    rc = ResponseConfidence(level=ConfidenceLevel.CONFIRMED, evidence=evidence)
    assert rc.level is ConfidenceLevel.CONFIRMED
    assert len(rc.evidence) == 1


# ---------------------------------------------------------------------------
# ResponseConfidence — model validation
# ---------------------------------------------------------------------------


def test_response_confidence_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ResponseConfidence(level=ConfidenceLevel.UNKNOWN, bad_field="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Git evidence — never auto-fabricated
# ---------------------------------------------------------------------------


def test_git_commit_source_type_exists_but_is_not_auto_populated():
    """git_commit enum value exists for future use but should never appear
    in automatically generated evidence."""
    # No constructor creates git_commit evidence automatically.
    rc1 = ResponseConfidence.from_source_code("f.py")
    rc2 = ResponseConfidence.from_chunks([_make_included_chunk("c1")])
    rc3 = ResponseConfidence.unknown()

    for rc in [rc1, rc2, rc3]:
        for ev in rc.evidence:
            assert ev.source_type is not EvidenceSourceType.GIT_COMMIT, (
                "git_commit evidence was fabricated automatically — this is not allowed."
            )


# ---------------------------------------------------------------------------
# ResponseConfidence — unknown_with_source_code (free-text path)
# ---------------------------------------------------------------------------


def test_unknown_with_source_code_gives_unknown():
    """unknown_with_source_code must return UNKNOWN, not CONFIRMED."""
    rc = ResponseConfidence.unknown_with_source_code("src/main.py")
    assert rc.level is ConfidenceLevel.UNKNOWN


def test_unknown_with_source_code_evidence_is_non_empty():
    rc = ResponseConfidence.unknown_with_source_code("src/main.py")
    assert len(rc.evidence) == 1


def test_unknown_with_source_code_evidence_source_type():
    rc = ResponseConfidence.unknown_with_source_code("src/main.py")
    assert rc.evidence[0].source_type is EvidenceSourceType.SOURCE_CODE


def test_unknown_with_source_code_preserves_file_path():
    rc = ResponseConfidence.unknown_with_source_code("app/calc.py")
    assert rc.evidence[0].file_path == "app/calc.py"


def test_unknown_with_source_code_none_file_path():
    rc = ResponseConfidence.unknown_with_source_code(None)
    assert rc.level is ConfidenceLevel.UNKNOWN
    assert rc.evidence[0].file_path is None


def test_unknown_with_source_code_with_notes():
    rc = ResponseConfidence.unknown_with_source_code("f.py", notes="Free-text response.")
    assert rc.notes == "Free-text response."


def test_unknown_with_source_code_not_confirmed():
    """Source code availability alone must NEVER produce CONFIRMED for free-text path."""
    rc = ResponseConfidence.unknown_with_source_code("any/file.py")
    assert rc.level is not ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# ResponseConfidence — unknown_with_chunks (free-text path)
# ---------------------------------------------------------------------------


def test_unknown_with_chunks_empty_gives_unknown():
    rc = ResponseConfidence.unknown_with_chunks([])
    assert rc.level is ConfidenceLevel.UNKNOWN
    assert rc.evidence == []


def test_unknown_with_chunks_with_chunks_gives_unknown():
    """Retrieved chunks available to the model do NOT confirm free-text claims."""
    chunks = [_make_included_chunk("c1"), _make_included_chunk("c2")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert rc.level is ConfidenceLevel.UNKNOWN


def test_unknown_with_chunks_not_confirmed():
    chunks = [_make_included_chunk("c1")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert rc.level is not ConfidenceLevel.CONFIRMED


def test_unknown_with_chunks_evidence_count_matches():
    chunks = [_make_included_chunk("c1"), _make_included_chunk("c2")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert len(rc.evidence) == 2


def test_unknown_with_chunks_evidence_source_type_is_retrieved_chunk():
    chunks = [_make_included_chunk("c1")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert rc.evidence[0].source_type is EvidenceSourceType.RETRIEVED_CHUNK


def test_unknown_with_chunks_preserves_file_path():
    chunks = [_make_included_chunk("c1", file_path="src/auth.py")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert rc.evidence[0].file_path == "src/auth.py"


def test_unknown_with_chunks_preserves_chunk_id():
    chunks = [_make_included_chunk("my-chunk")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert rc.evidence[0].chunk_id == "my-chunk"


def test_unknown_with_chunks_no_fabricated_evidence():
    chunks = [_make_included_chunk("real-chunk")]
    rc = ResponseConfidence.unknown_with_chunks(chunks)
    assert all(e.chunk_id == "real-chunk" for e in rc.evidence)


def test_unknown_with_chunks_with_notes():
    rc = ResponseConfidence.unknown_with_chunks(
        [_make_included_chunk("c1")], notes="Free-text path."
    )
    assert rc.notes == "Free-text path."
