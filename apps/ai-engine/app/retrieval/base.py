"""Provider-independent retrieval interface and data model (Task 7).

This module defines:

- ``RetrievedChunk`` — the typed unit of retrieved context.
- ``RetrieverBase`` — abstract interface every concrete retriever must implement.

Design principles
-----------------
- **Provider-independent** — no vector database, no embedding service.  The
  interface accepts a plain string query and returns a ranked list of chunks.
- **Deterministic** — implementations must return the same result for the same
  input so tests are reproducible.
- **Easy to replace** — a future semantic/vector retriever only needs to
  implement ``RetrieverBase.retrieve``; the orchestrator and reasoning layer
  need no changes.
- **Typed** — ``RetrievedChunk`` is a Pydantic model so it can be validated,
  serialised, and used directly in the reasoning prompt builder (Task 6).

Current limitation
------------------
No production vector database is used.  The ``InMemoryRetriever`` shipped in
``app.retrieval.memory`` performs keyword/lexical matching only and is intended
for development and testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field


class RetrievedChunk(BaseModel):
    """A single unit of retrieved context.

    Fields intentionally mirror the source locations used by the AST parser
    and repository scanner so they can be populated from those sources later.

    Attributes
    ----------
    chunk_id:
        Stable identifier for the chunk, e.g. a content hash or DB primary key.
    file_path:
        Repository-relative path of the file the content came from.
    symbol:
        Optional qualified symbol name, e.g. ``MyClass.my_method``.
    content:
        The actual text content (source snippet, doc comment, etc.).
    line_start:
        1-based first line of the chunk in its source file.
    line_end:
        1-based last line of the chunk in its source file.
    relevance_score:
        Retriever-assigned relevance in [0.0, 1.0].  Higher is more relevant.
    source_type:
        Origin label, e.g. ``"source_code"``, ``"docstring"``, ``"comment"``.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Stable unique identifier for this chunk.")
    file_path: str = Field(description="Repository-relative path of the source file.")
    symbol: str | None = Field(
        default=None,
        description="Optional qualified symbol name, e.g. 'MyClass.method'.",
    )
    content: str = Field(description="Text content of the chunk.")
    line_start: int | None = Field(default=None, ge=1, description="First line (1-based).")
    line_end: int | None = Field(default=None, ge=1, description="Last line (1-based).")
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Retriever-assigned relevance score in [0.0, 1.0].",
    )
    source_type: str = Field(
        default="source_code",
        description="Origin of the content, e.g. 'source_code', 'docstring', 'comment'.",
    )


class RetrieverBase(ABC):
    """Abstract interface for all retrieval implementations.

    Usage::

        retriever: RetrieverBase = InMemoryRetriever(corpus)
        chunks = retriever.retrieve(query="how does login work", top_k=5)
    """

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Return the *top_k* most relevant chunks for *query*.

        Parameters
        ----------
        query:
            Free-text retrieval query.
        top_k:
            Maximum number of chunks to return.  Implementations may return
            fewer if the corpus is smaller than *top_k*.

        Returns
        -------
        list[RetrievedChunk]
            Chunks sorted by descending ``relevance_score``.  The list is
            empty when no relevant content is found.
        """
