"""In-memory lexical retriever (Task 7).

This retriever performs **keyword / term-frequency matching** against an
in-memory corpus of ``RetrievedChunk`` objects.  It is intentionally simple:

- No external dependencies beyond Python's standard library.
- Fully deterministic — the same query always returns the same ranked list.
- Suitable for unit tests and local development.
- Designed to be replaced by a vector/semantic retriever later; only the
  ``RetrieverBase.retrieve`` interface needs to be re-implemented.

Algorithm
---------
For each chunk the retriever counts how many query tokens (normalised to
lower-case) appear in the chunk's content (also normalised).  The score is
the proportion of matched tokens relative to the total number of unique query
tokens, giving a value in [0.0, 1.0].

Chunks with a score of 0 (no token overlap) are excluded from results.
Results are sorted by descending score; ties are broken by insertion order
(deterministic).

Limitations
-----------
- No stemming or lemmatisation.
- No TF-IDF or BM25 weighting.
- Not suitable for production retrieval with large corpora.
"""

from __future__ import annotations

import re
from typing import Sequence

from app.retrieval.base import RetrieverBase, RetrievedChunk


# Symbol boost fraction added when a query token exactly matches the chunk's
# symbol name (or any dot-separated part of it, e.g. "ClassName" from
# "ClassName.method").  The boost is capped so the final score stays ≤ 1.0.
# Value rationale: 0.1 is enough to break ties and lift an exact symbol match
# above a longer chunk whose body happens to contain the same word, without
# making the boost large enough to overwhelm a poor content match.
_SYMBOL_BOOST = 0.10


def _tokenise(text: str) -> list[str]:
    """Split *text* into lower-case word tokens."""
    return re.findall(r"[a-z0-9_]+", text.lower())


def _score(chunk: RetrievedChunk, query_tokens: list[str]) -> float:
    """Return a relevance score for *chunk* against *query_tokens*.

    Algorithm
    ---------
    1. Token-overlap proportion: (matched unique query tokens) / (total unique
       query tokens).  This gives a base score in [0.0, 1.0].
    2. Symbol boost: if the chunk carries a ``symbol`` and at least one query
       token matches a part of that symbol (case-insensitive), add
       ``_SYMBOL_BOOST``.  The final score is capped at 1.0.

    The symbol boost is documented explicitly so ranking behaviour is not
    opaque: a result moves higher because the query contains the exact symbol
    name or a part of the qualified symbol (e.g. ``"login"`` matches
    ``"Auth.login"``).
    """
    if not query_tokens:
        return 0.0
    unique_query = set(query_tokens)
    content_tokens = set(_tokenise(chunk.content))
    matched = unique_query & content_tokens
    base = len(matched) / len(unique_query)

    # Symbol boost: lift chunks whose declared symbol exactly matches a query
    # token.  This makes "login" prefer chunks annotated symbol="login" or
    # symbol="AuthService.login" over chunks that merely mention the word.
    boost = 0.0
    if base > 0.0 and chunk.symbol:
        symbol_parts = set(_tokenise(chunk.symbol))
        if symbol_parts & unique_query:
            boost = _SYMBOL_BOOST

    return min(base + boost, 1.0)


class InMemoryRetriever(RetrieverBase):
    """Deterministic in-memory retriever for tests and development.

    Parameters
    ----------
    corpus:
        Sequence of ``RetrievedChunk`` objects to search.  The corpus is
        loaded at construction time and never mutated.

    Example::

        chunks = [
            RetrievedChunk(
                chunk_id="1",
                file_path="app/auth.py",
                content="def login(user, password): ...",
                source_type="source_code",
            )
        ]
        retriever = InMemoryRetriever(corpus=chunks)
        results = retriever.retrieve("login authentication", top_k=3)
    """

    def __init__(self, corpus: Sequence[RetrievedChunk]) -> None:
        self._corpus: list[RetrievedChunk] = list(corpus)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Return the *top_k* most relevant chunks for *query*.

        Chunks are scored by token overlap (see module docstring).
        Chunks with a score of 0 are excluded.

        Parameters
        ----------
        query:
            Free-text retrieval query.
        top_k:
            Maximum number of results to return.

        Returns
        -------
        list[RetrievedChunk]
            Chunks sorted by descending relevance score.  Empty list when
            there is no token overlap with any chunk.
        """
        query_tokens = _tokenise(query)
        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk in self._corpus:
            score = _score(chunk, query_tokens)
            if score > 0.0:
                scored.append((score, chunk))

        # Sort by descending score (stable sort preserves insertion order for ties).
        scored.sort(key=lambda t: t[0], reverse=True)

        # Return new chunk instances with updated relevance_score.
        results: list[RetrievedChunk] = []
        for score, chunk in scored[:top_k]:
            results.append(chunk.model_copy(update={"relevance_score": score}))
        return results
