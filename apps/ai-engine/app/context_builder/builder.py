"""Centralised context builder (Task 8).

Responsibilities
----------------
1. Accept a ``CodeUnderstandingRequest`` and an optional list of
   ``RetrievedChunk`` objects from the retrieval layer.
2. Assemble the relevant pieces of information that should be sent to the
   reasoning layer, in a well-defined, deterministic order.
3. Deduplicate retrieved chunks so the same content is never included twice.
4. Apply a hard character-level size cap so the context never exceeds the
   configured ``max_chars`` limit.
5. Preserve source attribution for every included chunk so the evidence
   layer can reference back to the original source.
6. Never invent repository facts — only include content that is explicitly
   supplied.

Design notes
------------
- **Provider-independent** — no LLM, no embedding service.
- **Deterministic** — same inputs always produce the same ``BuiltContext``.
- **Extensible** — the ``BuiltContext`` model contains an ``extra_sections``
  dict that future evidence types (Git, test, architecture) can populate
  without changing the core model.
- Does not modify the existing ``CodeUnderstandingRequest`` or any other
  existing schema.

Extension points (not yet implemented)
---------------------------------------
- Git evidence: add a ``git_sections`` field or populate ``extra_sections``.
- Test evidence: same approach.
- Architecture / relationship context: same approach.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.code_understanding import (
    AnalysisType,
    CodeUnderstandingRequest,
    ProgrammingLanguage,
)

if TYPE_CHECKING:
    from app.retrieval.base import RetrievedChunk

# ---------------------------------------------------------------------------
# Size limit
# ---------------------------------------------------------------------------

# Default hard cap on the total number of characters across all context
# sections that are assembled.  Callers may override this via the builder.
MAX_CONTEXT_CHARS: int = 80_000


# ---------------------------------------------------------------------------
# Typed context model
# ---------------------------------------------------------------------------


class IncludedChunk(BaseModel):
    """A retrieved chunk that was selected for inclusion in the context.

    Preserves attribution so the evidence layer can reference the source.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Stable identifier from the retrieval layer.")
    file_path: str = Field(description="Repository-relative file path.")
    symbol: str | None = Field(default=None, description="Qualified symbol name if available.")
    content: str = Field(description="Text content of the chunk.")
    line_start: int | None = Field(default=None, description="First line (1-based).")
    line_end: int | None = Field(default=None, description="Last line (1-based).")
    relevance_score: float = Field(
        default=0.0,
        description="Retriever-assigned relevance score [0.0, 1.0].",
    )
    source_type: str = Field(
        default="source_code",
        description="Origin label, e.g. 'source_code', 'docstring'.",
    )


class BuiltContext(BaseModel):
    """Assembled, deduplicated, size-capped context ready for the reasoning layer.

    Fields
    ------
    source_code:
        The submitted source code (always present).
    language:
        Programming language of the source code.
    file_path:
        Optional repository-relative path.
    question:
        Optional free-form question from the request.
    user_context:
        Optional supplementary context supplied by the caller.
    analyses:
        The requested analysis types.
    included_chunks:
        Retrieved chunks selected and deduplicated for inclusion, ordered
        by descending relevance score.
    truncated:
        ``True`` when content was dropped to satisfy ``max_chars``.
    extra_sections:
        Reserved for future evidence types (Git, test, architecture).
        Currently always empty.
    """

    model_config = ConfigDict(extra="forbid")

    source_code: str
    language: ProgrammingLanguage
    file_path: str | None = None
    question: str | None = None
    user_context: str | None = None
    analyses: list[AnalysisType] = Field(default_factory=list)
    included_chunks: list[IncludedChunk] = Field(default_factory=list)
    truncated: bool = False
    extra_sections: dict[str, str] = Field(
        default_factory=dict,
        description="Reserved for future evidence types (Git, test, architecture).",
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Stateless context assembler.

    Usage::

        builder = ContextBuilder(max_chars=80_000)
        context = builder.build(request, retrieved_chunks=chunks)

    Parameters
    ----------
    max_chars:
        Hard cap on the total number of characters across all assembled
        context sections.  Chunks that would push the total over the limit
        are dropped (highest-relevance chunks are included first).
    """

    def __init__(self, max_chars: int = MAX_CONTEXT_CHARS) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        self._max_chars = max_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        request: CodeUnderstandingRequest,
        retrieved_chunks: Sequence["RetrievedChunk"] | None = None,
    ) -> BuiltContext:
        """Assemble a ``BuiltContext`` from a request and optional chunks.

        Steps
        -----
        1. Count the characters occupied by the mandatory fields (source code,
           question, user context).
        2. Deduplicate retrieved chunks by ``chunk_id``.
        3. Sort chunks by descending relevance score (deterministic on ties
           via stable sort preserving original order).
        4. Include chunks in relevance order until the character budget is
           exhausted.
        5. Return a ``BuiltContext`` with ``truncated=True`` if any chunks
           were dropped.

        Parameters
        ----------
        request:
            A validated ``CodeUnderstandingRequest``.
        retrieved_chunks:
            Optional list of ``RetrievedChunk`` objects from the retrieval
            layer.  ``None`` and ``[]`` are both treated as no context.

        Returns
        -------
        BuiltContext
            Assembled context with attribution preserved.
        """
        # ── 1. Budget for mandatory fields ───────────────────────────────
        remaining = self._max_chars
        remaining -= len(request.source_code)
        if request.question:
            remaining -= len(request.question)
        if request.context:
            remaining -= len(request.context)

        # ── 2. Deduplicate chunks (preserve first occurrence order) ──────
        deduped = _deduplicate_chunks(retrieved_chunks or [])

        # ── 3. Sort by descending relevance (stable preserves input order
        #       for equal scores) ──────────────────────────────────────────
        sorted_chunks = sorted(deduped, key=lambda c: c.relevance_score, reverse=True)

        # ── 4. Include chunks within budget ──────────────────────────────
        included: list[IncludedChunk] = []
        truncated = False

        for chunk in sorted_chunks:
            chunk_len = len(chunk.content)
            if remaining < chunk_len:
                truncated = True
                continue  # skip — prefer relevant chunks; do not stop early
            remaining -= chunk_len
            included.append(
                IncludedChunk(
                    chunk_id=chunk.chunk_id,
                    file_path=chunk.file_path,
                    symbol=chunk.symbol,
                    content=chunk.content,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    relevance_score=chunk.relevance_score,
                    source_type=chunk.source_type,
                )
            )

        # Re-sort included chunks by descending relevance to preserve
        # meaningful ordering in the final context.
        included.sort(key=lambda c: c.relevance_score, reverse=True)

        # ── 5. Build the typed context ────────────────────────────────────
        return BuiltContext(
            source_code=request.source_code,
            language=request.language,
            file_path=request.file_path,
            question=request.question,
            user_context=request.context,
            analyses=list(request.analyses),
            included_chunks=included,
            truncated=truncated,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _deduplicate_chunks(
    chunks: Sequence["RetrievedChunk"],
) -> list["RetrievedChunk"]:
    """Return a deduplicated list preserving first-occurrence ordering.

    Deduplication is performed by ``chunk_id``.  If the same ``chunk_id``
    appears more than once, only the first occurrence is kept.
    """
    seen: set[str] = set()
    result: list["RetrievedChunk"] = []
    for chunk in chunks:
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            result.append(chunk)
    return result
