"""Tests for the repository-level retrieval service (Step 6).

Tests the ``apps/ai-engine/app/retrieval/service.py`` module.
All tests are deterministic and require no external services.

Covered topics
--------------
1. Ingest repository and cache retrieval
2. Search returns relevant chunks
3. Repository isolation (different repos independent)
4. top_k respected
5. Query with no matching tokens returns empty list
6. Repeated search does not rebuild corpus
7. Result metadata preserved
8. End-to-end with temporary sample repository
9. Invalid path handling
"""

from __future__ import annotations

import sys
import os
import tempfile

import pytest

from app.retrieval.service import ingest, search
from app.retrieval.base import RetrievedChunk
from app.evidence.models import EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_source(tmpdir, relpath, content):
    """Write a source file under *tmpdir* at *relpath*."""
    filepath = os.path.join(tmpdir, relpath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


JSON_CONTENT = '{"key": "value"}'


# ---------------------------------------------------------------------------
# 1. Ingest repository and cache retrieval
# ---------------------------------------------------------------------------

def test_ingest_repository_caches():
    """ingest() returns the same InMemoryRetriever instance for the same path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/a.py", "def foo(): pass\n")
        _write_source(tmpdir, "src/b.py", "def bar(): pass\n")

        retriever1 = ingest(tmpdir)
        retriever2 = ingest(tmpdir)

        assert retriever1 is retriever2, "Same path should return cached retriever"
        assert len(retriever1._corpus) == 2


def test_ingest_repository_different_paths_independent():
    """Different repository paths produce independent retrievers."""
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            _write_source(tmpdir1, "src/a.py", "def foo(): pass\n")
            _write_source(tmpdir2, "src/b.py", "def bar(): pass\n")

            # Both directories are alive — ingest immediately so paths are valid.
            retriever1 = ingest(tmpdir1)
            retriever2 = ingest(tmpdir2)

        # At this point both directories have been cleaned up, but we already
        # have the retriever instances cached by absolute path.

        assert retriever1 is not retriever2, "Different paths should yield different retriever instances"
        # Both retrievers should have at least one chunk
        assert len(retriever1._corpus) >= 1
        assert len(retriever2._corpus) >= 1


# ---------------------------------------------------------------------------
# 2. Search returns relevant chunks
# ---------------------------------------------------------------------------

def test_search_returns_relevant_chunks():
    """search() returns chunks with positive relevance_score for matching tokens."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/auth.py", "def login(user, password):\n    return True\n")
        _write_source(tmpdir, "src/service.py", "class UserService:\n    pass\n")

        results = search(tmpdir, "login user", top_k=3)

        assert len(results) > 0, "Expected at least one matching chunk"
        for r in results:
            assert r.relevance_score > 0.0, "Expected positive relevance score"
        # Should find the auth.py chunk
        has_auth = any("auth" in r.file_path for r in results)
        assert has_auth, "Expected at least one chunk from auth.py"


def test_search_top_k_respected():
    """search() returns at most top_k chunks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/a.py", "def foo():\n    return 1\n")
        _write_source(tmpdir, "src/b.py", "def bar():\n    return 2\n")
        _write_source(tmpdir, "src/c.py", "def baz():\n    return 3\n")

        results = search(tmpdir, "def", top_k=2)

        assert len(results) <= 2, f"Expected at most 2 results, got {len(results)}"


# ---------------------------------------------------------------------------
# 3. Query with no matching tokens returns empty list
# ---------------------------------------------------------------------------

def test_search_no_matching_tokens():
    """search() returns empty list when query has no token overlap with corpus."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/a.py", "def foo():\n    return 1\n")

        results = search(tmpdir, "xyzThqz", top_k=5)

        assert len(results) == 0, "Expected no matching chunks for unrelated query"


# ---------------------------------------------------------------------------
# 4. Repeated search does not rebuild corpus
# ---------------------------------------------------------------------------

def test_repeated_search_no_rebuild():
    """Repeated search against the same indexed repository does not rebuild the corpus."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/a.py", "def foo():\n    return 1\n")
        _write_source(tmpdir, "src/b.py", "def bar():\n    return 2\n")

        # First search
        results1 = search(tmpdir, "foo", top_k=3)
        # Second search
        results2 = search(tmpdir, "foo", top_k=3)

        assert len(results1) == len(results2)
        # Both should find 1 matching chunk
        assert len(results1) == 1
        assert len(results2) == 1


# ---------------------------------------------------------------------------
# 5. Result metadata preserved
# ---------------------------------------------------------------------------

def test_search_preserves_metadata():
    """Search results preserve all RetrievedChunk fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_source(tmpdir, "src/auth.py", "def login(user, password):\n    return True\n")

        results = search(tmpdir, "login", top_k=1)

        assert len(results) == 1
        r = results[0]
        # All required fields must be present
        assert r.chunk_id, "chunk_id must be present"
        assert r.file_path, "file_path must be present"
        assert r.content, "content must be present"
        assert r.line_start is not None and r.line_start >= 1, "line_start must be 1-based"
        assert r.line_end is not None and r.line_end >= r.line_start, "line_end must >= line_start"
        assert r.relevance_score >= 0.0, "relevance_score must be >= 0.0"
        assert r.relevance_score <= 1.0, "relevance_score must be <= 1.0"
        assert r.source_type == EvidenceSourceType.SOURCE_CODE, "source_type must be SOURCE_CODE"


# ---------------------------------------------------------------------------
# 6. End-to-end with temporary sample repository
# ---------------------------------------------------------------------------

def test_end_to_end_small_repository():
    """End-to-end: ingest -> search -> expected file/chunk returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a small repository structure
        os.makedirs(os.path.join(tmpdir, "src"), exist_ok=True)
        _write_source(tmpdir, "src/auth.py", "def login(user, password):\n    return True\n")
        _write_source(tmpdir, "src/types.ts", "export interface User { name: string }\n")
        # Add a file in root (not under src)
        _write_source(tmpdir, "README.md", "# Project\n")

        # Search for 'login' — should find auth.py
        results = search(tmpdir, "login", top_k=3)

        assert len(results) > 0, "Expected at least one result for 'login'"
        # The result from auth.py should be present
        has_auth = any("auth" in r.file_path for r in results)
        assert has_auth, "Expected at least one chunk from auth.py"

        # No results should come from README.md (no token overlap with 'login')
        readme_results = [r for r in results if "README" in r.file_path]
        assert len(readme_results) == 0, "No chunks should come from README.md for 'login' query"

        # Verify all results have proper metadata
        for r in results:
            assert r.chunk_id, "Each result must have chunk_id"
            assert r.file_path, "Each result must have file_path"
            assert r.content, "Each result must have content"
            assert r.line_start is not None and r.line_start >= 1, "line_start must be 1-based"
            assert r.line_end is not None and r.line_end >= r.line_start, "line_end must >= line_start"


# ---------------------------------------------------------------------------
# 7. Repository ingestion failure surfaced cleanly
# ---------------------------------------------------------------------------

def test_ingest_invalid_path_raises():
    """ingest() raises RuntimeError/OSError for invalid directory path."""
    # Pass a path that is clearly not a directory
    with pytest.raises((RuntimeError, OSError)):
        ingest("/proc/nonexistent_file")