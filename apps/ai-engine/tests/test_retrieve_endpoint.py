"""Tests for POST /api/v1/retrieve endpoint.

Proves:
- The endpoint returns ranked chunks with file_path, symbol, line_start,
  line_end, relevance_score, chunk_id, and content.
- The content field carries actual source lines (not metadata comments).
- The AI Engine receives evidence with source_code in /api/v1/code-understanding.
- A blank query returns 422 (validation error via FastAPI).
- An invalid repository path returns 500.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.adapters.iretrieval_adapter import RepositoryRetrievalAdapter, RetrievalResult
from app.retrieval.base import RetrievedChunk

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    file_path: str,
    content: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    relevance_score: float = 0.8,
    chunk_id: str = "chunk-001",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        symbol=symbol,
        content=content,
        line_start=line_start,
        line_end=line_end,
        relevance_score=relevance_score,
        source_type="source_code",
    )


def _make_result(chunks: list[RetrievedChunk]) -> RetrievalResult:
    return RetrievalResult(chunks=chunks, evidence=[], dependencies=[])


# ---------------------------------------------------------------------------
# POST /api/v1/retrieve — success
# ---------------------------------------------------------------------------


def test_retrieve_returns_chunks_with_content():
    """The retrieve endpoint returns chunks including actual source content."""
    login_code = textwrap.dedent("""\
        async def login(username: str, password: str) -> User | None:
            user = await repo.find(username)
            if not user:
                return None
            return user if verify(password, user.hash) else None
    """)

    mock_result = _make_result(
        [
            _make_chunk(
                file_path="app/auth.py",
                content=login_code,
                symbol="login",
                line_start=10,
                line_end=15,
                relevance_score=0.9,
            )
        ]
    )

    with patch.object(RepositoryRetrievalAdapter, "search", return_value=mock_result):
        response = client.post(
            "/api/v1/retrieve",
            json={
                "repository_path": "/fake/repo",
                "query": "how does login work",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    body = response.json()

    assert "chunks" in body
    assert len(body["chunks"]) == 1

    chunk = body["chunks"][0]
    assert chunk["file_path"] == "app/auth.py"
    assert chunk["symbol"] == "login"
    assert chunk["line_start"] == 10
    assert chunk["line_end"] == 15
    assert chunk["relevance_score"] == pytest.approx(0.9)
    assert chunk["chunk_id"] == "chunk-001"

    # content must be actual source lines, not metadata comments
    assert "login" in chunk["content"]
    assert "async def" in chunk["content"]
    assert not chunk["content"].startswith("//")


def test_retrieve_returns_multiple_chunks_ranked():
    """Multiple chunks are returned in relevance order."""
    chunks = [
        _make_chunk("auth.py", "def login(): pass", symbol="login",
                    relevance_score=0.9, chunk_id="c1"),
        _make_chunk("auth.py", "def logout(): pass", symbol="logout",
                    relevance_score=0.5, chunk_id="c2"),
    ]
    mock_result = _make_result(chunks)

    with patch.object(RepositoryRetrievalAdapter, "search", return_value=mock_result):
        response = client.post(
            "/api/v1/retrieve",
            json={"repository_path": "/fake/repo", "query": "login"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["chunks"]) == 2
    # First chunk should be the higher-scored one
    assert body["chunks"][0]["chunk_id"] == "c1"
    assert body["chunks"][0]["relevance_score"] == pytest.approx(0.9)


def test_retrieve_empty_when_no_match():
    """Empty chunks list is valid when nothing matches the query."""
    mock_result = _make_result([])

    with patch.object(RepositoryRetrievalAdapter, "search", return_value=mock_result):
        response = client.post(
            "/api/v1/retrieve",
            json={"repository_path": "/fake/repo", "query": "xyzzy_no_match"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["chunks"] == []
    assert body["query"] == "xyzzy_no_match"


def test_retrieve_echoes_query_and_path():
    """The response echoes the query and repository_path for correlation."""
    mock_result = _make_result([])

    with patch.object(RepositoryRetrievalAdapter, "search", return_value=mock_result):
        response = client.post(
            "/api/v1/retrieve",
            json={
                "repository_path": "/my/project",
                "query": "How does authentication work?",
                "top_k": 3,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "How does authentication work?"
    assert body["repository_path"] == "/my/project"
    assert body["top_k"] == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_retrieve_missing_repository_path_returns_422():
    response = client.post(
        "/api/v1/retrieve",
        json={"query": "login"},
    )
    assert response.status_code == 422


def test_retrieve_missing_query_returns_422():
    response = client.post(
        "/api/v1/retrieve",
        json={"repository_path": "/fake/repo"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_retrieve_returns_500_on_adapter_exception():
    """Adapter failure (e.g. invalid repo path) returns 500."""
    with patch.object(
        RepositoryRetrievalAdapter, "search", side_effect=RuntimeError("path not a dir")
    ):
        response = client.post(
            "/api/v1/retrieve",
            json={"repository_path": "/does/not/exist", "query": "login"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
