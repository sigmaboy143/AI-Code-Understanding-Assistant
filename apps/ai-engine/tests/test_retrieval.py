"""Tests for the retrieval/RAG foundation (Task 7).

All tests are deterministic and require no external services.

Coverage
--------
- RetrievedChunk model validation
- RetrieverBase abstract interface
- InMemoryRetriever: empty corpus, single match, multiple matches, top_k limit,
  relevance ordering, empty result, tie-breaking determinism
- RetrievedChunk integration with reasoning prompt (Task 6 extension point)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.retrieval.base import RetrieverBase, RetrievedChunk
from app.retrieval.memory import InMemoryRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(
    chunk_id: str,
    content: str,
    file_path: str = "src/code.py",
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    source_type: str = "source_code",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        symbol=symbol,
        content=content,
        line_start=line_start,
        line_end=line_end,
        source_type=source_type,
    )


# ---------------------------------------------------------------------------
# RetrievedChunk — model validation
# ---------------------------------------------------------------------------


def test_chunk_requires_chunk_id():
    with pytest.raises(ValidationError):
        RetrievedChunk(file_path="x.py", content="code")  # type: ignore[call-arg]


def test_chunk_requires_file_path():
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk_id="1", content="code")  # type: ignore[call-arg]


def test_chunk_requires_content():
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk_id="1", file_path="x.py")  # type: ignore[call-arg]


def test_chunk_defaults():
    chunk = _chunk("1", "some code")
    assert chunk.symbol is None
    assert chunk.line_start is None
    assert chunk.line_end is None
    assert chunk.relevance_score == 0.0
    assert chunk.source_type == "source_code"


def test_chunk_accepts_all_fields():
    chunk = RetrievedChunk(
        chunk_id="abc123",
        file_path="app/auth.py",
        symbol="Auth.login",
        content="def login(user, password): ...",
        line_start=10,
        line_end=25,
        relevance_score=0.87,
        source_type="docstring",
    )
    assert chunk.chunk_id == "abc123"
    assert chunk.symbol == "Auth.login"
    assert chunk.line_start == 10
    assert chunk.line_end == 25
    assert chunk.relevance_score == pytest.approx(0.87)
    assert chunk.source_type == "docstring"


def test_chunk_rejects_relevance_score_out_of_range():
    with pytest.raises(ValidationError):
        _chunk("1", "code").__class__(
            chunk_id="1",
            file_path="x.py",
            content="code",
            relevance_score=1.5,
        )


def test_chunk_rejects_zero_line_number():
    with pytest.raises(ValidationError):
        RetrievedChunk(
            chunk_id="1",
            file_path="x.py",
            content="code",
            line_start=0,
        )


def test_chunk_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RetrievedChunk(
            chunk_id="1",
            file_path="x.py",
            content="code",
            extra_field="bad",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# RetrieverBase — interface contract
# ---------------------------------------------------------------------------


def test_retriever_base_is_abstract():
    """RetrieverBase cannot be instantiated directly."""
    with pytest.raises(TypeError):
        RetrieverBase()  # type: ignore[abstract]


def test_in_memory_retriever_implements_interface():
    assert issubclass(InMemoryRetriever, RetrieverBase)


# ---------------------------------------------------------------------------
# InMemoryRetriever — empty corpus
# ---------------------------------------------------------------------------


def test_empty_corpus_returns_empty_list():
    retriever = InMemoryRetriever(corpus=[])
    assert retriever.retrieve("anything") == []


# ---------------------------------------------------------------------------
# InMemoryRetriever — empty/blank query
# ---------------------------------------------------------------------------


def test_blank_query_returns_empty_list():
    corpus = [_chunk("1", "def add(a, b): return a + b")]
    retriever = InMemoryRetriever(corpus=corpus)
    assert retriever.retrieve("") == []


# ---------------------------------------------------------------------------
# InMemoryRetriever — single match
# ---------------------------------------------------------------------------


def test_single_matching_chunk_returned():
    corpus = [_chunk("1", "def login(user, password): ...")]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login user")
    assert len(results) == 1
    assert results[0].chunk_id == "1"


def test_score_is_positive_for_matching_chunk():
    corpus = [_chunk("1", "def login(user, password): ...")]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login user")
    assert results[0].relevance_score > 0.0


def test_score_is_clamped_to_1():
    corpus = [_chunk("1", "login user password authentication")]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login user password authentication")
    assert results[0].relevance_score <= 1.0


# ---------------------------------------------------------------------------
# InMemoryRetriever — no match
# ---------------------------------------------------------------------------


def test_no_matching_chunk_returns_empty_list():
    corpus = [_chunk("1", "def add(a, b): return a + b")]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("authentication JWT token")
    assert results == []


# ---------------------------------------------------------------------------
# InMemoryRetriever — multiple chunks, relevance ordering
# ---------------------------------------------------------------------------


def test_most_relevant_chunk_is_first():
    corpus = [
        _chunk("low", "def unrelated_function(): pass"),
        _chunk("high", "def authenticate_user(token, password): verify(token)"),
    ]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("authenticate user token password")
    assert results[0].chunk_id == "high"


def test_multiple_matching_chunks_sorted_by_score():
    corpus = [
        _chunk("1", "login"),                               # 1/3 match
        _chunk("2", "login user password"),                  # 3/3 match
        _chunk("3", "login password"),                       # 2/3 match
    ]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login user password")
    assert [r.chunk_id for r in results] == ["2", "3", "1"]


# ---------------------------------------------------------------------------
# InMemoryRetriever — top_k limit
# ---------------------------------------------------------------------------


def test_top_k_limits_results():
    corpus = [_chunk(str(i), f"login user token {i}") for i in range(10)]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login user token", top_k=3)
    assert len(results) <= 3


def test_top_k_default_is_5():
    corpus = [_chunk(str(i), f"login authentication {i}") for i in range(10)]
    retriever = InMemoryRetriever(corpus=corpus)
    results = retriever.retrieve("login authentication")
    assert len(results) <= 5


# ---------------------------------------------------------------------------
# InMemoryRetriever — determinism
# ---------------------------------------------------------------------------


def test_same_query_same_results():
    corpus = [
        _chunk("a", "function authentication token"),
        _chunk("b", "class UserService login"),
    ]
    retriever = InMemoryRetriever(corpus=corpus)
    first = retriever.retrieve("authentication login")
    second = retriever.retrieve("authentication login")
    assert [r.chunk_id for r in first] == [r.chunk_id for r in second]


def test_original_chunk_relevance_score_not_mutated():
    """InMemoryRetriever must not mutate the original corpus chunks."""
    corpus = [_chunk("1", "login user")]
    retriever = InMemoryRetriever(corpus=corpus)
    retriever.retrieve("login user")
    # Original chunk in corpus must still have the default score.
    assert corpus[0].relevance_score == 0.0


# ---------------------------------------------------------------------------
# RetrievedChunk integration with reasoning prompt
# ---------------------------------------------------------------------------


def test_retrieved_chunks_appear_in_reasoning_prompt():
    """Chunks passed to build_reasoning_request must appear in the prompt."""
    from app.reasoning import build_reasoning_request
    from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest

    request = CodeUnderstandingRequest(
        source_code="def add(a, b): return a + b",
        language="python",
        analyses=[AnalysisType.EXPLANATION],
    )
    chunks = [
        RetrievedChunk(
            chunk_id="ctx1",
            file_path="src/math.py",
            symbol="add",
            content="Helper used by the calculator module.",
            relevance_score=0.9,
            source_type="docstring",
        )
    ]
    llm_req = build_reasoning_request(request, retrieved_chunks=chunks)
    user_content = llm_req.messages[1].content
    assert "src/math.py" in user_content
    assert "Helper used by the calculator module." in user_content


def test_no_retrieved_chunks_no_retrieved_section():
    """When no chunks are provided the 'Retrieved context' heading is absent."""
    from app.reasoning import build_reasoning_request
    from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest

    request = CodeUnderstandingRequest(
        source_code="def add(a, b): return a + b",
        language="python",
        analyses=[AnalysisType.EXPLANATION],
    )
    llm_req = build_reasoning_request(request, retrieved_chunks=None)
    assert "Retrieved context" not in llm_req.messages[1].content
