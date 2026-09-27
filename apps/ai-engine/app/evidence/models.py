"""Evidence and confidence models (Task 9).

Evidence model
--------------
An ``EvidenceItem`` identifies *where* supporting information came from.
It is attached to a response to show that claims are grounded in real data,
not fabricated.

Supported evidence source types
--------------------------------
- ``source_code``      — directly from the submitted source code
- ``retrieved_chunk``  — from a retrieved context chunk (RAG)
- ``file``             — from a referenced file path
- ``documentation``    — from inline documentation / docstrings
- ``test``             — from test code (reserved; not fabricated)
- ``git_commit``       — from Git history (reserved; never fabricated)

Confidence levels
-----------------
CONFIRMED:
    Directly supported by at least one piece of supplied or retrieved
    evidence.  Do NOT mark a statement CONFIRMED unless evidence exists.

INFERRED:
    Reasoned from available evidence but not explicitly established.
    Use when the statement is a plausible conclusion, not a direct
    observation.

UNKNOWN:
    Insufficient evidence to make any determination.  When no relevant
    evidence is available this is the correct and honest state.

Constraints
-----------
- Evidence items are never invented.  If evidence does not exist, represent
  the absence explicitly using the UNKNOWN confidence level.
- ``git_commit`` source type is defined for future use.  No Git evidence is
  fabricated automatically.
- There is no numeric confidence score because there is no real calculation
  to back one up at this milestone.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Evidence source type
# ---------------------------------------------------------------------------


class EvidenceSourceType(str, Enum):
    """Supported origins of evidence in a response.

    ``git_commit`` is defined for future use.  The system never fabricates
    Git evidence automatically.
    """

    SOURCE_CODE = "source_code"
    RETRIEVED_CHUNK = "retrieved_chunk"
    FILE = "file"
    DOCUMENTATION = "documentation"
    TEST = "test"
    GIT_COMMIT = "git_commit"  # Future-ready; never auto-populated


# ---------------------------------------------------------------------------
# Confidence level
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, Enum):
    """Three-state confidence representation.

    CONFIRMED:
        Directly supported by supplied or retrieved evidence.
    INFERRED:
        Reasoned from available evidence but not explicitly established.
    UNKNOWN:
        Insufficient evidence to make any determination.
    """

    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Evidence item
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A single piece of supporting evidence for a claim in a response.

    Fields
    ------
    source_type:
        Where the evidence came from (see ``EvidenceSourceType``).
    file_path:
        Repository-relative file path, when available.
    line_start:
        1-based first line of the evidence in the file, when available.
    line_end:
        1-based last line of the evidence in the file, when available.
    chunk_id:
        Identifier of the retrieved chunk, when the source is a chunk.
    description:
        Short human-readable reference, e.g. "Function 'add' defined here."
    """

    model_config = ConfigDict(extra="forbid")

    source_type: EvidenceSourceType = Field(
        description="Origin of the evidence."
    )
    file_path: str | None = Field(
        default=None,
        description="Repository-relative file path, if applicable.",
    )
    line_start: int | None = Field(
        default=None,
        ge=1,
        description="First line of the evidence (1-based), if applicable.",
    )
    line_end: int | None = Field(
        default=None,
        ge=1,
        description="Last line of the evidence (1-based), if applicable.",
    )
    chunk_id: str | None = Field(
        default=None,
        description="Chunk identifier, when source_type is retrieved_chunk.",
    )
    description: str | None = Field(
        default=None,
        description="Short human-readable reference for this evidence item.",
    )


# ---------------------------------------------------------------------------
# Response confidence
# ---------------------------------------------------------------------------


class ResponseConfidence(BaseModel):
    """Confidence level and supporting evidence attached to a response.

    This model is designed to be embedded in ``CodeUnderstandingResponse``
    (or a future versioned schema) without breaking the existing contract.

    Fields
    ------
    level:
        One of CONFIRMED, INFERRED, or UNKNOWN.  Defaults to UNKNOWN so
        that the absence of evidence is explicit, never silently omitted.
    evidence:
        List of evidence items that support the confidence level.
        Empty when ``level`` is UNKNOWN.
    notes:
        Optional free-text note, e.g. explaining why confidence is UNKNOWN.
    """

    model_config = ConfigDict(extra="forbid")

    level: ConfidenceLevel = Field(
        default=ConfidenceLevel.UNKNOWN,
        description="Confidence state: CONFIRMED, INFERRED, or UNKNOWN.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items that support this confidence level.",
    )
    notes: str | None = Field(
        default=None,
        description="Optional note explaining confidence determination.",
    )

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def unknown(cls, notes: str | None = None) -> "ResponseConfidence":
        """Return an UNKNOWN confidence with no evidence."""
        return cls(level=ConfidenceLevel.UNKNOWN, evidence=[], notes=notes)

    @classmethod
    def from_chunks(
        cls,
        chunks: list,  # list[IncludedChunk] — avoided circular import
        *,
        notes: str | None = None,
    ) -> "ResponseConfidence":
        """Build a ResponseConfidence from a list of included context chunks.

        Rules
        -----
        - If no chunks are provided → UNKNOWN.
        - If chunks are provided → CONFIRMED (directly retrieved evidence).
        - Each chunk generates one EvidenceItem with source attribution.

        Use this constructor only when you are representing that a specific
        structured claim is directly backed by these retrieved chunks.  Do NOT
        use it to represent the confidence of a free-text LLM response as a
        whole — a free-text answer cannot be claim-mapped to evidence and
        should instead use ``unknown_with_evidence`` or ``unknown``.

        Parameters
        ----------
        chunks:
            List of ``IncludedChunk`` objects from the context builder.
        notes:
            Optional explanatory note.
        """
        if not chunks:
            return cls.unknown(notes=notes)

        evidence: list[EvidenceItem] = []
        for chunk in chunks:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.RETRIEVED_CHUNK,
                    file_path=chunk.file_path,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    chunk_id=chunk.chunk_id,
                    description=chunk.symbol or chunk.source_type,
                )
            )

        return cls(
            level=ConfidenceLevel.CONFIRMED,
            evidence=evidence,
            notes=notes,
        )

    @classmethod
    def from_source_code(
        cls,
        file_path: str | None,
        *,
        notes: str | None = None,
    ) -> "ResponseConfidence":
        """Build a CONFIRMED confidence backed by submitted source code.

        Use this constructor only when the claim being annotated is directly
        and completely supported by the submitted source code itself — for
        example when reporting a structural fact extracted programmatically
        from the code.

        Do NOT use this to represent the confidence of a free-text LLM answer
        about the code.  The LLM answer is not claim-mapped to evidence, so
        the whole-response confidence must remain UNKNOWN even when source code
        is available.  Use ``unknown_with_source_code`` for that case.

        Parameters
        ----------
        file_path:
            Repository-relative path of the submitted source code, if known.
        notes:
            Optional explanatory note.
        """
        evidence = EvidenceItem(
            source_type=EvidenceSourceType.SOURCE_CODE,
            file_path=file_path,
            description="Submitted source code.",
        )
        return cls(
            level=ConfidenceLevel.CONFIRMED,
            evidence=[evidence],
            notes=notes,
        )

    @classmethod
    def unknown_with_source_code(
        cls,
        file_path: str | None,
        *,
        notes: str | None = None,
    ) -> "ResponseConfidence":
        """Return UNKNOWN confidence while recording available source-code evidence.

        Use this for free-text LLM responses when source code was submitted.
        The response confidence is UNKNOWN because the free-text answer has not
        been claim-mapped to evidence.  The evidence list records what was
        available so callers can see what the model had to work with.

        Parameters
        ----------
        file_path:
            Repository-relative path of the submitted source code, if known.
        notes:
            Optional explanatory note.
        """
        evidence = EvidenceItem(
            source_type=EvidenceSourceType.SOURCE_CODE,
            file_path=file_path,
            description="Submitted source code (available to model; claims not individually verified).",
        )
        return cls(
            level=ConfidenceLevel.UNKNOWN,
            evidence=[evidence],
            notes=notes,
        )

    @classmethod
    def unknown_with_chunks(
        cls,
        chunks: list,  # list[IncludedChunk] — avoided circular import
        *,
        notes: str | None = None,
    ) -> "ResponseConfidence":
        """Return UNKNOWN confidence while recording available retrieved-chunk evidence.

        Use this for free-text LLM responses when retrieved context chunks were
        included in the prompt.  The response confidence is UNKNOWN because the
        free-text answer has not been claim-mapped to evidence.  The evidence
        list records which chunks were available.

        Parameters
        ----------
        chunks:
            List of ``IncludedChunk`` objects from the context builder.
        notes:
            Optional explanatory note.
        """
        if not chunks:
            return cls.unknown(notes=notes)

        evidence: list[EvidenceItem] = []
        for chunk in chunks:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.RETRIEVED_CHUNK,
                    file_path=chunk.file_path,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    chunk_id=chunk.chunk_id,
                    description=chunk.symbol or chunk.source_type,
                )
            )

        return cls(
            level=ConfidenceLevel.UNKNOWN,
            evidence=evidence,
            notes=notes,
        )
