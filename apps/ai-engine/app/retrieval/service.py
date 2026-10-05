"""Repository-level retrieval service.

Responsibilities
----------------
1. Keep an in-memory map of repository paths to InMemoryRetriever instances.
2. Expose ``ingest(repository_path)`` to scan a repository and build a retriever corpus.
3. Expose ``search(repository_path, query, top_k)`` to retrieve chunks for a
   given repository using a user query.
4. Provide repository isolation — a query against repository A never retrieves
   chunks from repository B.
5. Avoid rebuilding the corpus for every query if a reusable in-memory index
   already exists.

Design notes
------------
- Repository path is the key into the in-memory map.  The same absolute path
  always maps to the same retriever; different paths are independent.
- The ``InMemoryRetriever`` scoring algorithm (token‑overlap proportion) is
  unchanged — it is not rebuilt per‑query.
- ``BuiltContext`` and ``OrchestratorService`` already accept an optional
  ``retrieved_chunks`` sequence, so the retrieval layer can inject RAG context
  without changing the orchestration loop.
- This module is deliberately **provider‑agnostic** and **dependency‑free**
  beyond the existing ``app.retrieval`` types.

Limitations
-----------
- The corpus lives only in process memory.  Process restarts clear all indexed
  repositories.
- Very large repositories may consume significant RAM when the full corpus
  is kept in memory.
- No semantic search or vector similarity is performed — only the existing
  lexical (keyword / term‑frequency) scoring is used.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

from app.ingestion import ingest_repository
from app.retrieval.base import RetrievedChunk, RetrieverBase
from app.retrieval.memory import InMemoryRetriever


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

# Mapping: repository-absolute path → InMemoryRetriever corpus.
# Populated at startup empty and grown incrementally as ``ingest`` is called.
_repo_index: Dict[str, InMemoryRetriever] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest(repository_path: str) -> InMemoryRetriever:
    """Ingest an entire repository and return the corresponding retriever.

    The resulting ``InMemoryRetriever`` is cached keyed by the repository's
    absolute path so that subsequent calls with the same path return the
    same instance without re‑scanning the disk.

    Parameters
    ----------
    repository_path:
        Absolute or relative path to the root of a repository to scan.
        Relative paths are resolved to absolute via ``os.path.abspath``.

    Returns
    -------
    InMemoryRetriever
        A retriever over the ``RetrievedChunk`` corpus produced by
        ``ingest_repository``.

    Raises
    ------
    RuntimeError
        If ``root_path`` is not a valid directory.
    """
    abs_path = os.path.abspath(repository_path)
    if not os.path.isdir(abs_path):
        raise RuntimeError(
            f"Repository path is not a valid directory: {abs_path}"
        )

    # Return cached retriever if already indexed
    if abs_path in _repo_index:
        return _repo_index[abs_path]

    # Scan and chunk the repository
    chunks: list[RetrievedChunk] = ingest_repository(abs_path, max_chars_per_chunk=800)

    # Build the retriever and cache it
    retriever: InMemoryRetriever = InMemoryRetriever(corpus=chunks)
    _repo_index[abs_path] = retriever

    return retriever


def search(
    repository_path: str,
    query: str,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Retrieve the *top_k* most relevant chunks for *query* from
    *repository_path*.

    If the repository has not yet been indexed, it is automatically ingested.

    Parameters
    ----------
    repository_path:
        Absolute or relative path to the repository root.
    query:
        Free‑text retrieval query.
    top_k:
        Maximum number of chunks to return.  Defaults to 5.

    Returns
    -------
    list[RetrievedChunk]
        Chunks sorted by descending ``relevance_score``.  Empty list when
        there is no token overlap with any chunk in the corpus.
    """
    retriever = ingest(repository_path)
    return retriever.retrieve(query, top_k=top_k)