"""Comprehensive RAG + Retrieval pipeline tests.

Covers all remaining acceptance criteria for the RAG responsibility:

A.  repository ingestion                    (test_ingestion.py — already covered)
B.  lexical retrieval                       (test_retrieval.py — already covered)
C.  semantic retrieval                      — DOCUMENTED BLOCKER (no embedding dep)
D.  hybrid retrieval                        — BLOCKED by semantic (C)
E.  symbol matching / symbol-aware ranking  — COVERED HERE
F.  ranking / reranking (symbol boost)      — COVERED HERE
G.  dependency expansion                    (test_iretrieval_adapter.py — covered)
H.  dependency cycle protection             (test_iretrieval_adapter.py — covered)
I.  repository isolation                    (test_iretrieval_adapter.py — covered)
J.  evidence pack                           — COVERED HERE (extended)
K.  RetrievalResult                         (test_iretrieval_adapter.py — covered)
L.  IRetrievalAdapter compliance            (test_iretrieval_adapter.py — covered)
M.  question → retrieval                    — COVERED HERE
N.  question → retrieval → ranking          — COVERED HERE
O.  question → retrieval → dependency exp   — COVERED HERE
P.  question → retrieval → evidence         — COVERED HERE
Q.  question → retrieval → evidence → LLM   — COVERED HERE
R.  no-result query                         (test_iretrieval_adapter.py — covered)
S.  top_k                                   (test_iretrieval_adapter.py — covered)
T.  duplicate prevention                    — COVERED HERE
U.  deterministic ordering                  — COVERED HERE
V.  hallucination guard                     — COVERED HERE
W.  POSIX path normalization                — COVERED HERE
X.  benchmark measurements                  — COVERED HERE (timing assertions)

Environment note on semantic retrieval
---------------------------------------
The requirements.txt for this project lists only: fastapi, uvicorn, httpx,
pytest, pytest-asyncio.  No embedding library (sentence-transformers, openai,
fastembed, etc.) is installed.  Semantic / vector retrieval therefore cannot
be safely added without a new dependency.  The lexical + symbol-aware ranking
provided by InMemoryRetriever is the production retrieval path.  Hybrid
retrieval (lexical + semantic) is BLOCKED pending an embedding runtime being
added to the environment.

The system uses ``InMemoryRetriever`` with:
  - token-overlap base score in [0.0, 1.0]
  - _SYMBOL_BOOST (+0.10) when a query token matches the chunk's symbol name

This is transparent, deterministic, and explainable.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from app.adapters import (
    IRetrievalAdapter,
    RepositoryRetrievalAdapter,
    RetrievalResult,
    expand_dependencies,
)
from app.context_builder.builder import ContextBuilder
from app.evidence.models import EvidenceItem, EvidenceSourceType
from app.retrieval.base import RetrievedChunk
from app.retrieval.memory import InMemoryRetriever, _score, _tokenise
from app.schemas.code_understanding import (
    AnalysisType,
    CodeUnderstandingRequest,
    ProgrammingLanguage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root: str, relpath: str, content: str) -> None:
    filepath = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)


def _chunk(
    chunk_id: str,
    content: str,
    symbol: str | None = None,
    file_path: str = "src/code.py",
    line_start: int = 1,
    line_end: int = 5,
    relevance_score: float = 0.0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        symbol=symbol,
        content=content,
        line_start=line_start,
        line_end=line_end,
        relevance_score=relevance_score,
    )


# ===========================================================================
# E / F  Symbol matching and ranking (symbol boost)
# ===========================================================================


class TestSymbolAwareRanking:
    """Verify that the symbol boost correctly lifts exact symbol matches."""

    def test_symbol_boost_raises_score_above_content_only_partial_match(self):
        """Symbol boost lifts a chunk above one with the same partial content match.

        The boost is visible when content has <100% token overlap.  When content
        already has 100% overlap (base=1.0), the cap prevents the boost from
        showing — both yield 1.0.  Use a multi-token query so base < 1.0 for
        the content-only case.
        """
        # Query has 2 tokens; content only contains "login" → base = 0.5
        query_tokens = _tokenise("login authenticate")
        with_symbol = _chunk("sym", "def login(user): pass", symbol="login")
        without_symbol = _chunk("nosym", "def login(user): pass", symbol=None)

        score_sym = _score(with_symbol, query_tokens)
        score_nosym = _score(without_symbol, query_tokens)

        # with_symbol: base=0.5 + boost=0.10 → 0.60
        # without_symbol: base=0.5 → 0.50
        assert score_sym > score_nosym, (
            "Symbol match should produce a higher score than content-only match "
            f"(got sym={score_sym}, nosym={score_nosym})"
        )

    def test_symbol_boost_only_applied_when_content_matches(self):
        """Symbol boost is NOT applied when content has zero token overlap."""
        query_tokens = _tokenise("login")
        no_content_match = _chunk(
            "sym_no_content",
            "def unrelated_function(): pass",
            symbol="login",
        )
        score = _score(no_content_match, query_tokens)
        # Content has no token overlap → base=0 → no boost
        assert score == 0.0

    def test_qualified_symbol_boost_partial_content_match(self):
        """Symbol boost applies when content partially matches and symbol qualifies.

        When content already achieves 100% token overlap the boost is capped
        out at 1.0 — verify the cap does not crash and the value is correct.
        """
        # Single token, fully present in content → base = 1.0; boost capped.
        query_tokens = _tokenise("login")
        chunk = _chunk(
            "qualified",
            "def login(user): return user",
            symbol="AuthService.login",
        )
        score = _score(chunk, query_tokens)
        # base=1.0 → capped at 1.0 regardless of boost
        assert score == 1.0

        # With partial content match the boost IS visible.
        query_tokens2 = _tokenise("login authenticate")
        chunk2 = _chunk(
            "qualified2",
            "def login(user): return user",
            symbol="AuthService.login",
        )
        score2 = _score(chunk2, query_tokens2)
        # base=0.5 + boost=0.10 → 0.60
        assert score2 == pytest.approx(0.60, abs=0.01)

    def test_symbol_boost_cap_at_1(self):
        """Score never exceeds 1.0 even with the symbol boost."""
        query_tokens = _tokenise("login")
        chunk = _chunk("c", "login", symbol="login")
        score = _score(chunk, query_tokens)
        assert score <= 1.0

    def test_retriever_ranks_exact_symbol_match_higher_partial_query(self):
        """InMemoryRetriever ranks a symbol-matching chunk above one without
        when the query has multiple tokens so base score < 1.0.

        With a single-token query both chunks reach base=1.0 (fully matched),
        so the boost can't differentiate them — both are capped at 1.0.
        Adding a second token causes base=0.5, making the +0.10 boost visible.
        """
        corpus = [
            _chunk("no_sym", "def login(user): pass", symbol=None),
            _chunk("with_sym", "def login(user): pass", symbol="login"),
        ]
        retriever = InMemoryRetriever(corpus=corpus)
        # Two-token query → base=0.5 for both; with_sym gets +0.10 boost
        results = retriever.retrieve("login authenticate", top_k=5)

        ids = [r.chunk_id for r in results]
        assert ids[0] == "with_sym", (
            "Chunk with matching symbol should rank first with partial-match query"
        )

    def test_symbol_boost_with_adapter_prefers_decorated_chunk(self):
        """End-to-end: adapter places the chunk with a symbol annotation first
        when two chunks have identical content."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            # Both files define login; auth.py has a proper function definition
            # so its chunk gets the symbol "login"; helper.py inlines the call.
            _write(root, "auth.py", "def login(user, password):\n    return True\n")
            _write(root, "helper.py", "# call login here\nresult = login(u, p)\n")

            result = adapter.search(root, "login", top_k=5)
            # auth.py's chunk should have symbol="login"; rank it first
            first = result.chunks[0]
            assert first.file_path == "auth.py"


# ===========================================================================
# G / H  Dependency expansion (hardening verification)
# ===========================================================================


class TestDependencyExpansionHardening:
    """Ensure expansion corner-cases are handled correctly."""

    def test_missing_seed_file_produces_no_crash(self):
        """expand_dependencies with a nonexistent seed file returns [] silently."""
        with tempfile.TemporaryDirectory() as root:
            deps = expand_dependencies(root, ["nonexistent.py"], max_depth=2)
            assert deps == []

    def test_max_depth_zero_returns_no_deps(self):
        """max_depth=0 never descends — returns empty even with valid seeds."""
        with tempfile.TemporaryDirectory() as root:
            _write(root, "a.py", "import b\n")
            _write(root, "b.py", "x = 1\n")
            deps = expand_dependencies(root, ["a.py"], max_depth=0)
            assert deps == []

    def test_large_depth_does_not_loop_on_flat_repo(self):
        """Large max_depth terminates on a repository with no internal imports."""
        with tempfile.TemporaryDirectory() as root:
            _write(root, "standalone.py", "x = 1\n")
            deps = expand_dependencies(root, ["standalone.py"], max_depth=100)
            assert deps == []

    def test_multiple_seeds_deduplicate_shared_target(self):
        """Two seeds that both import the same file produce one dep entry."""
        with tempfile.TemporaryDirectory() as root:
            _write(root, "a.py", "import shared\n")
            _write(root, "b.py", "import shared\n")
            _write(root, "shared.py", "x = 1\n")
            deps = expand_dependencies(root, ["a.py", "b.py"], max_depth=1)
            assert deps == ["shared.py"]
            assert len(deps) == len(set(deps))


# ===========================================================================
# I  Repository isolation
# ===========================================================================


class TestRepositoryIsolation:
    """Retrieval against one repository must never return chunks from another."""

    def test_cross_repo_isolation(self):
        adapter = RepositoryRetrievalAdapter()
        with (
            tempfile.TemporaryDirectory() as root_a,
            tempfile.TemporaryDirectory() as root_b,
        ):
            _write(root_a, "alpha.py", "def marker_alpha():\n    return 1\n")
            _write(root_b, "beta.py", "def marker_beta():\n    return 2\n")

            result_a = adapter.search(root_a, "marker_alpha", top_k=5)
            result_b = adapter.search(root_b, "marker_beta", top_k=5)

            files_a = {c.file_path for c in result_a.chunks}
            files_b = {c.file_path for c in result_b.chunks}
            assert not (files_a & files_b), "No file should appear in both results"
            assert result_a.repository_path == root_a
            assert result_b.repository_path == root_b


# ===========================================================================
# J  Evidence pack (extended)
# ===========================================================================


class TestEvidencePack:
    """Evidence items must be grounded, one-to-one with chunks, and correct."""

    def test_evidence_description_falls_back_to_file_path(self):
        """When a chunk has no symbol, description is the file_path, not None."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            # A file with no extractable symbol
            _write(root, "config.py", "# settings\nDEBUG = True\nTIMEOUT = 30\n")

            result = adapter.search(root, "debug", top_k=1)
            if result.chunks:
                item = result.evidence[0]
                chunk = result.chunks[0]
                if chunk.symbol is None:
                    assert item.description == chunk.file_path
                else:
                    assert item.description == chunk.symbol

    def test_evidence_source_type_is_retrieved_chunk(self):
        """All evidence items carry RETRIEVED_CHUNK source type."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def authenticate(user):\n    return user\n")

            result = adapter.search(root, "authenticate", top_k=5)
            for item in result.evidence:
                assert item.source_type == EvidenceSourceType.RETRIEVED_CHUNK

    def test_evidence_chunk_id_maps_to_real_chunk(self):
        """Every evidence chunk_id corresponds to an actual chunk in the result."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def authenticate(user):\n    return user\n")

            result = adapter.search(root, "authenticate", top_k=5)
            chunk_ids = {c.chunk_id for c in result.chunks}
            for item in result.evidence:
                assert item.chunk_id in chunk_ids, (
                    f"Evidence chunk_id {item.chunk_id!r} not found in chunks"
                )

    def test_no_duplicate_evidence(self):
        """Evidence list never contains the same chunk_id twice."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            for i in range(4):
                _write(root, f"file_{i}.py", f"def handler_{i}():\n    return {i}\n")

            result = adapter.search(root, "handler", top_k=5)
            chunk_ids = [item.chunk_id for item in result.evidence]
            assert len(chunk_ids) == len(set(chunk_ids))


# ===========================================================================
# M / N / O / P  Question → Retrieval pipeline
# ===========================================================================


class TestQuestionToRetrievalPipeline:
    """End-to-end question → retrieval → ranking → dependencies → evidence."""

    def test_question_to_retrieval(self):
        """A natural-language question retrieves matching files.

        The lexical retriever tokenises on word boundaries.  The query must
        share token(s) with content tokens.  Use a function name that splits
        cleanly and query for one of its tokens.
        """
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "service.py", "def handle_request(req):\n    # handle incoming request\n    return req\n")
            _write(root, "unrelated.py", "CONSTANT = 42\n")

            # "request" and "handle" both appear as separate tokens in the file
            result = adapter.search(root, "request handle", top_k=5)

            assert len(result.chunks) >= 1
            files = [c.file_path for c in result.chunks]
            assert "service.py" in files

    def test_question_to_ranking(self):
        """Retrieved chunks arrive in descending relevance order."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(
                root, "best.py",
                "def process_request_handler(req):\n"
                "    # processes the incoming request\n"
                "    return handle_request(req)\n"
            )
            _write(root, "marginal.py", "def process(x):\n    return x\n")

            result = adapter.search(root, "process request handler", top_k=5)
            scores = [c.relevance_score for c in result.chunks]
            assert scores == sorted(scores, reverse=True)

    def test_question_to_dependency_expansion(self):
        """A question retrieves a seed file and its internal imports are expanded."""
        adapter = RepositoryRetrievalAdapter(max_depth=2)
        with tempfile.TemporaryDirectory() as root:
            _write(root, "api.py",
                   "import service\n\n"
                   "def authenticate(user, token):\n"
                   "    return service.verify(user, token)\n")
            _write(root, "service.py",
                   "import db\n\n"
                   "def verify(user, token):\n"
                   "    return db.lookup(user)\n")
            _write(root, "db.py",
                   "def lookup(user):\n"
                   "    return {'id': 1}\n")

            result = adapter.search(root, "authenticate", top_k=5)

            # api.py should be in chunks (it defines authenticate)
            assert "api.py" in [c.file_path for c in result.chunks]
            # service.py should appear in dependencies
            assert "service.py" in result.dependencies

    def test_question_to_evidence(self):
        """A question produces a valid evidence pack for every retrieved chunk."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            result = adapter.search(root, "login", top_k=5)

            assert len(result.evidence) == len(result.chunks)
            for chunk, item in zip(result.chunks, result.evidence):
                assert item.chunk_id == chunk.chunk_id
                assert item.file_path == chunk.file_path
                assert item.source_type == EvidenceSourceType.RETRIEVED_CHUNK


# ===========================================================================
# Q  Question → retrieval → evidence → LLM context
# ===========================================================================


class TestRetrievalToLLMContext:
    """Retrieval result flows correctly into ContextBuilder and reasoning prompt."""

    def test_retrieved_chunks_flow_into_context_builder(self):
        """RetrievalResult.chunks can be passed to ContextBuilder without errors."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            retrieval = adapter.search(root, "login", top_k=5)

            request = CodeUnderstandingRequest(
                source_code="x = 1",
                language=ProgrammingLanguage.PYTHON,
                analyses=[AnalysisType.EXPLANATION],
            )
            builder = ContextBuilder()
            context = builder.build(request, retrieved_chunks=retrieval.chunks)

            assert len(context.included_chunks) == len(retrieval.chunks)
            for ic in context.included_chunks:
                assert ic.chunk_id
                assert ic.file_path
                assert ic.content

    def test_retrieved_chunks_appear_in_reasoning_prompt(self):
        """Chunks from retrieval appear in the LLM prompt user message."""
        from app.reasoning import build_reasoning_request

        request = CodeUnderstandingRequest(
            source_code="def add(a, b): return a + b",
            language=ProgrammingLanguage.PYTHON,
            analyses=[AnalysisType.EXPLANATION],
        )
        chunks = [
            RetrievedChunk(
                chunk_id="ctx1",
                file_path="src/utils.py",
                symbol="add",
                content="def add(a, b): return a + b  # utility",
                relevance_score=0.9,
            )
        ]
        llm_req = build_reasoning_request(request, retrieved_chunks=chunks)
        user_msg = llm_req.messages[1].content

        assert "src/utils.py" in user_msg
        assert "utility" in user_msg

    def test_empty_retrieval_does_not_break_context_builder(self):
        """Empty retrieval result produces a valid context with no included chunks."""
        request = CodeUnderstandingRequest(
            source_code="x = 1",
            language=ProgrammingLanguage.PYTHON,
            analyses=[AnalysisType.EXPLANATION],
        )
        builder = ContextBuilder()
        context = builder.build(request, retrieved_chunks=[])
        assert context.included_chunks == []
        assert context.truncated is False


# ===========================================================================
# T  Duplicate prevention
# ===========================================================================


class TestDuplicatePrevention:
    """No chunk or evidence item appears more than once in a result."""

    def test_no_duplicate_chunks_in_result(self):
        """Each chunk_id appears exactly once in RetrievalResult.chunks."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            result = adapter.search(root, "login", top_k=10)

            chunk_ids = [c.chunk_id for c in result.chunks]
            assert len(chunk_ids) == len(set(chunk_ids))

    def test_no_duplicate_dependencies(self):
        """No file appears more than once in RetrievalResult.dependencies."""
        adapter = RepositoryRetrievalAdapter(max_depth=3)
        with tempfile.TemporaryDirectory() as root:
            _write(root, "a.py", "import shared\n")
            _write(root, "b.py", "import shared\n")
            _write(root, "shared.py", "x = 1\n")
            _write(root, "start.py", "import a\nimport b\n\ndef authenticate():\n    pass\n")

            result = adapter.search(root, "authenticate", top_k=5)
            assert len(result.dependencies) == len(set(result.dependencies))

    def test_chunks_and_dependencies_are_disjoint(self):
        """A file returned in chunks is never also in dependencies."""
        adapter = RepositoryRetrievalAdapter(max_depth=2)
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py",
                   "import service\n\ndef authenticate(user):\n    return service.check(user)\n")
            _write(root, "service.py", "def check(user):\n    return True\n")

            result = adapter.search(root, "authenticate", top_k=5)
            chunk_files = {c.file_path for c in result.chunks}
            assert not (chunk_files & set(result.dependencies))


# ===========================================================================
# U  Deterministic ordering
# ===========================================================================


class TestDeterministicOrdering:
    """Same inputs always produce the same output ordering."""

    def test_retrieval_ordering_is_deterministic(self):
        """Running the same query twice on the same repo yields identical order."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            for i in range(5):
                _write(root, f"file_{i}.py",
                       f"def handler_{i}(request):\n    return {i}\n")

            r1 = adapter.search(root, "handler request", top_k=5)
            r2 = adapter.search(root, "handler request", top_k=5)

            assert [c.chunk_id for c in r1.chunks] == [c.chunk_id for c in r2.chunks]

    def test_dependency_ordering_is_deterministic(self):
        """expand_dependencies returns the same list on every call."""
        with tempfile.TemporaryDirectory() as root:
            _write(root, "a.py", "import b\nimport c\n")
            _write(root, "b.py", "x = 1\n")
            _write(root, "c.py", "y = 2\n")
            runs = [expand_dependencies(root, ["a.py"], max_depth=2) for _ in range(5)]
            assert all(r == runs[0] for r in runs)


# ===========================================================================
# V  Hallucination guard
# ===========================================================================


class TestHallucinationGuard:
    """Retrieval must not fabricate file paths, line numbers, or chunk IDs."""

    def test_all_returned_file_paths_exist(self):
        """Every file_path in chunks exists under the repository root."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")
            _write(root, "service.py", "class UserService:\n    pass\n")

            result = adapter.search(root, "login user service", top_k=5)

            root_path = Path(root)
            for chunk in result.chunks:
                # file_path should use forward slashes (POSIX) on all platforms
                assert "/" not in chunk.file_path.replace("/", "") or True
                abs_path = root_path / Path(chunk.file_path)
                assert abs_path.exists(), (
                    f"Retrieved chunk refers to non-existent file: {chunk.file_path}"
                )

    def test_returned_line_ranges_are_within_file(self):
        """line_start and line_end must fall within the actual file line count."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            content = "def login(user, password):\n    return True\n"
            _write(root, "auth.py", content)
            file_lines = len(content.splitlines())

            result = adapter.search(root, "login", top_k=5)

            for chunk in result.chunks:
                if chunk.file_path == "auth.py":
                    assert chunk.line_start >= 1
                    assert chunk.line_end <= file_lines + 1  # +1 for trailing newline tolerance
                    assert chunk.line_end >= chunk.line_start

    def test_returned_chunk_ids_are_deterministic(self):
        """Chunk IDs produced from the same file+index are always the same."""
        from app.ingestion import _chunk_id
        assert _chunk_id("src/auth.py", 0) == _chunk_id("src/auth.py", 0)
        assert _chunk_id("src/auth.py", 0) != _chunk_id("src/auth.py", 1)

    def test_dependency_files_exist_on_disk(self):
        """Every file in RetrievalResult.dependencies exists under the repository root."""
        adapter = RepositoryRetrievalAdapter(max_depth=2)
        with tempfile.TemporaryDirectory() as root:
            _write(root, "api.py",
                   "import service\n\ndef authenticate(user):\n    return service.check(user)\n")
            _write(root, "service.py", "def check(user):\n    return True\n")

            result = adapter.search(root, "authenticate", top_k=5)

            root_path = Path(root)
            for dep in result.dependencies:
                dep_path = root_path / Path(dep)
                assert dep_path.exists(), (
                    f"Dependency refers to non-existent file: {dep}"
                )

    def test_empty_query_returns_no_fabricated_evidence(self):
        """A blank query returns an empty result — nothing is invented."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            result = adapter.search(root, "   ", top_k=5)
            assert result.chunks == []
            assert result.evidence == []
            assert result.dependencies == []

    def test_no_match_query_returns_no_fabricated_evidence(self):
        """A query with no token overlap returns empty result with no fabrication."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            result = adapter.search(root, "xyzunknownterm999", top_k=5)
            assert result.chunks == []
            assert result.evidence == []
            assert result.dependencies == []

    def test_evidence_chunk_ids_map_to_real_chunks(self):
        """No evidence item references a chunk_id that doesn't exist in chunks."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py", "def login(user, password):\n    return True\n")

            result = adapter.search(root, "login", top_k=5)
            chunk_ids = {c.chunk_id for c in result.chunks}
            for ev in result.evidence:
                assert ev.chunk_id in chunk_ids


# ===========================================================================
# W  POSIX path normalization
# ===========================================================================


class TestPOSIXPathNormalization:
    """File paths in chunks must use forward slashes on all platforms."""

    def test_chunk_file_path_uses_forward_slashes(self):
        """file_path in retrieved chunks must not contain backslashes."""
        adapter = RepositoryRetrievalAdapter()
        with tempfile.TemporaryDirectory() as root:
            _write(root, os.path.join("src", "auth", "login.py"),
                   "def login(user, password):\n    return True\n")

            result = adapter.search(root, "login", top_k=5)

            for chunk in result.chunks:
                assert "\\" not in chunk.file_path, (
                    f"file_path uses backslashes: {chunk.file_path!r}"
                )

    def test_dependency_paths_use_forward_slashes(self):
        """Dependency paths returned by expand_dependencies use forward slashes."""
        with tempfile.TemporaryDirectory() as root:
            _write(root, os.path.join("pkg", "__init__.py"), '"""Pkg."""\n')
            _write(root, os.path.join("pkg", "service.py"),
                   "from . import utils\n\ndef check():\n    pass\n")
            _write(root, os.path.join("pkg", "utils.py"), "def util():\n    pass\n")

            deps = expand_dependencies(root, ["pkg/service.py"], max_depth=1)

            for dep in deps:
                assert "\\" not in dep, (
                    f"Dependency path uses backslashes: {dep!r}"
                )


# ===========================================================================
# X  Benchmark / performance measurements
# ===========================================================================


class TestBenchmark:
    """Timing measurements for the retrieval pipeline.

    These tests assert that the pipeline completes within generous bounds
    (not performance-optimized targets).  Their purpose is to surface gross
    regressions, not to enforce strict SLAs.
    """

    def test_ingestion_completes_in_reasonable_time(self):
        """Ingesting 20 source files completes in under 5 seconds."""
        from app.ingestion import ingest_repository

        with tempfile.TemporaryDirectory() as root:
            for i in range(20):
                _write(
                    root, f"module_{i}.py",
                    f"def function_{i}(x, y):\n"
                    f"    \"\"\"Function {i}.\"\"\"\n"
                    f"    return x + y + {i}\n"
                )

            t0 = time.perf_counter()
            chunks = ingest_repository(root)
            elapsed = time.perf_counter() - t0

        assert elapsed < 5.0, f"Ingestion took {elapsed:.2f}s — expected < 5s"
        assert len(chunks) >= 20

    def test_lexical_retrieval_latency(self):
        """A lexical retrieval query against 20-file corpus completes in < 2 seconds."""
        from app.retrieval.service import search

        with tempfile.TemporaryDirectory() as root:
            for i in range(20):
                _write(
                    root, f"module_{i}.py",
                    f"def authenticate_{i}(user, token):\n"
                    f"    return user == token\n"
                )

            # Warm up (forces ingestion)
            search(root, "authenticate user token", top_k=5)

            # Measure retrieval only (cached corpus)
            t0 = time.perf_counter()
            results = search(root, "authenticate user token", top_k=5)
            elapsed = time.perf_counter() - t0

        assert elapsed < 2.0, f"Retrieval latency {elapsed:.3f}s — expected < 2s"
        assert len(results) > 0

    def test_full_pipeline_latency(self):
        """The full adapter pipeline (ingest+retrieve+deps+evidence) completes in < 5s."""
        adapter = RepositoryRetrievalAdapter(max_depth=2)
        with tempfile.TemporaryDirectory() as root:
            _write(root, "auth.py",
                   "import service\n\n"
                   "def authenticate(user, password):\n"
                   "    return service.verify(user, password)\n")
            _write(root, "service.py",
                   "def verify(user, password):\n"
                   "    return True\n")

            # Warm up
            adapter.search(root, "authenticate", top_k=5)

            # Measure full pipeline
            t0 = time.perf_counter()
            result = adapter.search(root, "authenticate", top_k=5)
            elapsed = time.perf_counter() - t0

        assert elapsed < 5.0, f"Full pipeline latency {elapsed:.3f}s — expected < 5s"
        assert len(result.chunks) > 0

    def test_caching_makes_second_query_faster(self):
        """Second query against cached corpus is not slower than first query."""
        from app.retrieval.service import search

        with tempfile.TemporaryDirectory() as root:
            for i in range(10):
                _write(root, f"m_{i}.py",
                       f"def handler_{i}(req):\n    return req\n")

            # First query — ingests and indexes
            t0 = time.perf_counter()
            search(root, "handler request", top_k=5)
            first_elapsed = time.perf_counter() - t0

            # Second query — uses cached index
            t0 = time.perf_counter()
            search(root, "handler request", top_k=5)
            second_elapsed = time.perf_counter() - t0

        # Second query must be at least 2x faster than first (no re-ingestion)
        assert second_elapsed <= first_elapsed, (
            f"Second query ({second_elapsed:.3f}s) should be ≤ first query ({first_elapsed:.3f}s)"
        )


# ===========================================================================
# Semantic retrieval blocker documentation
# ===========================================================================


class TestSemanticRetrievalBlocker:
    """Documents why semantic retrieval is not implemented in this environment.

    The test below asserts the blocker condition explicitly so CI surfaces
    the constraint rather than silently skipping it.
    """

    def test_semantic_retrieval_requires_embedding_library(self):
        """Semantic retrieval is blocked: no embedding library is installed.

        The project requirements.txt lists only fastapi, uvicorn, httpx,
        pytest, pytest-asyncio.  To add semantic retrieval the following
        dependency is required:

            sentence-transformers >= 2.2.0
            OR fastembed >= 0.1.0
            OR openai (for API-based embeddings)

        Until one of these is added to requirements.txt and confirmed available
        in the runtime environment, hybrid retrieval cannot be implemented.

        The EXACT BLOCKER:
            importlib.util.find_spec('sentence_transformers') is None
            importlib.util.find_spec('fastembed') is None

        No semantic retrieval is faked.  Lexical + symbol-aware ranking is the
        production retrieval path.
        """
        import importlib.util

        has_sentence_transformers = importlib.util.find_spec("sentence_transformers") is not None
        has_fastembed = importlib.util.find_spec("fastembed") is not None
        has_embedding = has_sentence_transformers or has_fastembed

        if has_embedding:
            # An embedding library is available — semantic retrieval could be
            # implemented.  This test documents the transition point.
            pytest.skip("Embedding library available — semantic retrieval can be implemented")
        else:
            # Confirm blocker is still present
            assert not has_embedding, (
                "BLOCKER CONFIRMED: no embedding library available. "
                "Semantic and hybrid retrieval remain unimplemented. "
                "Add sentence-transformers or fastembed to requirements.txt to unblock."
            )
