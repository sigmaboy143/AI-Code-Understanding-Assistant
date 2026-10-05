"""Focused tests for the concrete IRetrievalAdapter (Step 7).

Tests the CURRENT implementation in
``apps/ai-engine/app/adapters/iretrieval_adapter.py``.

All tests are deterministic, use temporary fixture repositories created through
``tempfile`` (matching ``test_ingestion.py`` / ``test_retrieval_service.py``),
and require no external services, network, or LLM.

Covered topics
--------------
1.  Interface contract — ``IRetrievalAdapter`` is abstract and unimplementable
2.  ``RepositoryRetrievalAdapter`` implements ``search``
3.  ``RetrievalResult`` Pydantic validation
4.  ``RetrievalResult`` rejects unknown fields
5.  Question -> retrieval
6.  Relevant files returned
7.  Symbol metadata preserved
8.  Relevance ordering preserved
9.  Repository isolation
10. Empty search result
11. top_k respected
12. Dependency expansion
13. Dependency ordering deterministic
14. Duplicate dependencies removed
15. Cyclic dependencies protected
16. max dependency depth enforced
17. Unresolved dependencies ignored
18. Evidence pack created
19. File/line/chunk metadata preserved
20. Full pipeline: question -> retrieval -> ranking -> deps -> evidence
"""

from __future__ import annotations

import os
import tempfile

import pytest
from pydantic import ValidationError

from app.adapters import (
    IRetrievalAdapter,
    RepositoryRetrievalAdapter,
    RetrievalResult,
    expand_dependencies,
)
from app.evidence.models import EvidenceItem, EvidenceSourceType
from app.retrieval.base import RetrievedChunk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root: str, relpath: str, content: str) -> str:
    """Write *content* to *relpath* under *root*.  Returns the absolute path."""
    filepath = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write(content)
    return filepath


# --- Fixture 1: linear internal-import chain (for depth/ordering tests) -----
#
#   auth_controller.py -> auth_service.py -> jwt_service.py -> repo.py
#
# Depth 1 reaches auth_service; depth 2 also reaches jwt_service; depth 3 also
# reaches repo.  This lets one fixture prove the bound precisely.

CHAIN_CONTROLLER = '''"""Login entry point."""

import auth_service


def login(username, password):
    """Authenticate a user."""
    return auth_service.login(username, password)
'''

CHAIN_SERVICE = '''"""Authentication service."""

import jwt_service


def login(username, password):
    """Delegate token minting to the JWT service."""
    return jwt_service.mint(username)
'''

CHAIN_JWT = '''"""JWT service."""

import repository


def mint(username):
    """Look the user up in the repository."""
    return repository.find(username)
'''

CHAIN_REPOSITORY = '''"""User repository."""


def find(username):
    """Return the stored user record."""
    return {"username": username}
'''


def _make_chain_repo(root: str) -> None:
    """Create the linear dependency chain fixture under *root*."""
    _write(root, "auth_controller.py", CHAIN_CONTROLLER)
    _write(root, "auth_service.py", CHAIN_SERVICE)
    _write(root, "jwt_service.py", CHAIN_JWT)
    _write(root, "repository.py", CHAIN_REPOSITORY)


# --- Fixture 2: package-style relative imports -----------------------------
#
#   pkg/api/controller.py  -> from ..services.user import UserService
#   pkg/services/user.py
#
# Exercises ``from ..services.user import X`` and the ``__init__.py`` target.

PKG_CONTROLLER = '''"""Package controller."""

from ..services.user import UserService


def handler():
    """Delegate to the user service."""
    return UserService.load()
'''

PKG_USER_SERVICE = '''"""User service."""


class UserService:
    @staticmethod
    def load():
        return None
'''

PKG_INIT = '"""Package marker."""\n'


def _make_package_repo(root: str) -> None:
    """Create the package-relative-import fixture under *root*."""
    _write(root, "pkg/__init__.py", PKG_INIT)
    _write(root, "pkg/api/__init__.py", PKG_INIT)
    _write(root, "pkg/api/controller.py", PKG_CONTROLLER)
    _write(root, "pkg/services/__init__.py", PKG_INIT)
    _write(root, "pkg/services/user.py", PKG_USER_SERVICE)


# --- Fixture 3: cyclic imports ---------------------------------------------

CYCLE_A = '''"""Cycle A."""


def a():
    from . import b
    return b.b()
'''

CYCLE_B = '''"""Cycle B."""


def b():
    from . import a
    return a.a()
'''


def _make_cycle_repo(root: str) -> None:
    """Create a two-file import cycle under *root*."""
    _write(root, "a.py", CYCLE_A)
    _write(root, "b.py", CYCLE_B)


# ---------------------------------------------------------------------------
# 1. Interface contract
# ---------------------------------------------------------------------------


def test_iretrieval_adapter_is_abstract():
    """IRetrievalAdapter cannot be instantiated — it is a real ABC."""
    assert IRetrievalAdapter.__abstractmethods__ == frozenset({"search"})

    with pytest.raises(TypeError):
        IRetrievalAdapter()  # type: ignore[abstract]


def test_iretrieval_adapter_subclass_must_implement_search():
    """A subclass that omits search() also remains abstract."""
    # IRetrievalAdapter already derives from ABC, so ABC must not be repeated
    # ahead of it in the bases (that would be an inconsistent MRO).
    class Incomplete(IRetrievalAdapter):
        pass

    assert "search" in Incomplete.__abstractmethods__
    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_repository_retrieval_adapter_implements_search():
    """RepositoryRetrievalAdapter satisfies the interface and is instantiable."""
    adapter = RepositoryRetrievalAdapter()

    assert isinstance(adapter, IRetrievalAdapter)
    assert IRetrievalAdapter in type(adapter).__mro__
    assert callable(adapter.search)
    # The concrete class clears the abstract set.
    assert not getattr(type(adapter), "__abstractmethods__", frozenset())


# ---------------------------------------------------------------------------
# 2. RetrievalResult Pydantic contract
# ---------------------------------------------------------------------------


def test_retrieval_result_is_pydantic_with_defaults():
    """RetrievalResult validates as a Pydantic model with empty defaults."""
    result = RetrievalResult()

    assert result.chunks == []
    assert result.evidence == []
    assert result.dependencies == []
    assert result.repository_path is None
    assert result.query is None
    assert result.top_k == 5


def test_retrieval_result_preserves_all_fields():
    """All supported fields round-trip through validation."""
    chunk = RetrievedChunk(chunk_id="c1", file_path="src/a.py", content="x = 1\n")
    item = EvidenceItem(
        source_type=EvidenceSourceType.RETRIEVED_CHUNK,
        file_path="src/a.py",
        chunk_id="c1",
    )

    result = RetrievalResult(
        chunks=[chunk],
        evidence=[item],
        dependencies=["src/b.py"],
        repository_path="/repo",
        query="how does a work",
        top_k=3,
    )

    assert result.chunks[0].chunk_id == "c1"
    assert result.evidence[0].chunk_id == "c1"
    assert result.dependencies == ["src/b.py"]
    assert result.repository_path == "/repo"
    assert result.query == "how does a work"
    assert result.top_k == 3


def test_retrieval_result_rejects_unknown_fields():
    """extra="forbid" rejects any field outside the declared contract."""
    with pytest.raises(ValidationError):
        RetrievalResult(unexpected_field="fabricated")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 3. Question -> retrieval, and file selection
# ---------------------------------------------------------------------------


def test_question_returns_relevant_file():
    """A question about login retrieves the file that implements login."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")
        _write(root, "unrelated.py", "def compute_totals(rows):\n    return sum(rows)\n")

        result = adapter.search(root, "login", top_k=5)

        assert len(result.chunks) >= 1
        assert any(c.file_path == "auth.py" for c in result.chunks)
        assert result.query == "login"


def test_relevant_file_selection_excludes_unrelated_files():
    """Files with no token overlap are never returned."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")
        _write(root, "unrelated.py", "def compute_totals(rows):\n    return sum(rows)\n")

        result = adapter.search(root, "login", top_k=5)

        assert "unrelated.py" not in [c.file_path for c in result.chunks]


# ---------------------------------------------------------------------------
# 4. Symbol / metadata preservation
# ---------------------------------------------------------------------------


def test_symbol_metadata_preserved():
    """Chunk symbols extracted during ingestion survive retrieval."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "login", top_k=1)

        assert len(result.chunks) == 1
        assert result.chunks[0].symbol == "login"


def test_file_line_and_chunk_metadata_preserved():
    """file_path, line range, chunk_id, source_type, and content all survive."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "login", top_k=1)
        chunk = result.chunks[0]

        assert chunk.file_path == "auth.py"
        assert chunk.line_start == 1
        assert chunk.line_end is not None and chunk.line_end >= 1
        assert chunk.chunk_id
        assert chunk.source_type == EvidenceSourceType.SOURCE_CODE
        assert "def login" in chunk.content


# ---------------------------------------------------------------------------
# 5. Ranking
# ---------------------------------------------------------------------------


def test_relevance_ordering_preserved():
    """Chunks arrive sorted by descending relevance_score."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        # Three files, each matching a different number of query tokens.
        _write(root, "all_three.py", "def alpha():\n    return 'alpha beta gamma'\n")
        _write(root, "two_only.py", "def alpha():\n    return 'alpha beta'\n")
        _write(root, "one_only.py", "def alpha():\n    return 'alpha'\n")

        result = adapter.search(root, "alpha beta gamma", top_k=5)

        scores = [c.relevance_score for c in result.chunks]
        assert scores == sorted(scores, reverse=True)
        assert result.chunks[0].file_path == "all_three.py"
        assert scores[0] > scores[-1]


def test_repeated_search_is_deterministic():
    """The same question twice yields identical ranked output."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")
        _write(root, "other.py", "def login_other():\n    return False\n")

        first = adapter.search(root, "login", top_k=5)
        second = adapter.search(root, "login", top_k=5)

        assert [c.chunk_id for c in first.chunks] == [c.chunk_id for c in second.chunks]
        assert [c.relevance_score for c in first.chunks] == [
            c.relevance_score for c in second.chunks
        ]


# ---------------------------------------------------------------------------
# 6. Repository isolation
# ---------------------------------------------------------------------------


def test_repository_isolation():
    """A query against repo A never returns chunks from repo B."""
    adapter = RepositoryRetrievalAdapter()
    with (
        tempfile.TemporaryDirectory() as root_a,
        tempfile.TemporaryDirectory() as root_b,
    ):
        _write(root_a, "alpha.py", "def marker_alpha():\n    return 1\n")
        _write(root_b, "beta.py", "def marker_beta():\n    return 2\n")

        result_a = adapter.search(root_a, "marker_alpha", top_k=5)
        result_b = adapter.search(root_b, "marker_beta", top_k=5)

        assert [c.file_path for c in result_a.chunks] == ["alpha.py"]
        assert [c.file_path for c in result_b.chunks] == ["beta.py"]
        assert result_a.repository_path == root_a
        assert result_b.repository_path == root_b


# ---------------------------------------------------------------------------
# 7. Empty result / blank query / top_k
# ---------------------------------------------------------------------------


def test_no_match_query_returns_empty_result():
    """A question matching nothing returns a valid, fully empty result."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "zzzznotpresentzzzz", top_k=5)

        assert result.chunks == []
        assert result.evidence == []
        assert result.dependencies == []
        assert result.repository_path == root


def test_blank_query_returns_empty_result_without_fabrication():
    """A blank query short-circuits to empty lists and still echoes the query."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "   ", top_k=5)

        assert result.chunks == []
        assert result.evidence == []
        assert result.dependencies == []


def test_top_k_respected():
    """No more than top_k chunks are returned."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        for index in range(6):
            _write(root, f"file_{index}.py", f"def shared():\n    return {index}\n")

        result = adapter.search(root, "shared", top_k=2)

        assert len(result.chunks) == 2
        assert result.top_k == 2


# ---------------------------------------------------------------------------
# 8. Dependency expansion
# ---------------------------------------------------------------------------


def test_dependency_expansion_follows_internal_imports():
    """A retrieved file's internal imports resolve to real files on disk.

    The query token "authenticate" occurs only in the controller, so the seeds
    are exactly ``["auth_controller.py"]`` and the dependency chain beyond it is
    fully visible.
    """
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        result = adapter.search(root, "authenticate", top_k=5)

        assert [c.file_path for c in result.chunks] == ["auth_controller.py"]
        assert result.dependencies == ["auth_service.py", "jwt_service.py"]


def test_dependencies_exclude_already_retrieved_files():
    """A file returned both as a chunk and as a dependency is reported once.

    Seeds come from the retrieved chunks, so any file already in ``chunks`` is
    excluded from ``dependencies``.  This keeps the two lists disjoint and stops
    the same file being announced twice.
    """
    adapter = RepositoryRetrievalAdapter(max_depth=3)
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        # "login" matches the controller *and* the service, so both are seeds.
        result = adapter.search(root, "login", top_k=5)

        chunk_files = {c.file_path for c in result.chunks}
        assert {"auth_controller.py", "auth_service.py"} <= chunk_files

        # Dependencies report only what retrieval did not already return.
        assert not (chunk_files & set(result.dependencies))
        assert result.dependencies == ["jwt_service.py", "repository.py"]


def test_dependency_expansion_respects_max_depth():
    """Depth 1 stops at the first hop; depth 2 and 3 reach further."""
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        assert expand_dependencies(root, ["auth_controller.py"], max_depth=0) == []
        assert expand_dependencies(root, ["auth_controller.py"], max_depth=1) == [
            "auth_service.py"
        ]
        assert expand_dependencies(root, ["auth_controller.py"], max_depth=2) == [
            "auth_service.py",
            "jwt_service.py",
        ]
        assert expand_dependencies(root, ["auth_controller.py"], max_depth=3) == [
            "auth_service.py",
            "jwt_service.py",
            "repository.py",
        ]


def test_adapter_honours_configured_max_depth():
    """RepositoryRetrievalAdapter applies its configured max_depth."""
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        shallow = RepositoryRetrievalAdapter(max_depth=1).search(root, "authenticate", top_k=5)
        deep = RepositoryRetrievalAdapter(max_depth=3).search(root, "authenticate", top_k=5)

        assert shallow.dependencies == ["auth_service.py"]
        assert deep.dependencies == [
            "auth_service.py",
            "jwt_service.py",
            "repository.py",
        ]


def test_dependency_expansion_resolves_relative_package_imports():
    """``from ..services.user import X`` resolves to the real file."""
    with tempfile.TemporaryDirectory() as root:
        _make_package_repo(root)

        deps = expand_dependencies(root, ["pkg/api/controller.py"], max_depth=1)

        assert deps == ["pkg/services/user.py"]


def test_dependency_expansion_resolves_dunder_init_target():
    """A package directory import resolves to its ``__init__.py``."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "pkg/__init__.py", '"""Package."""\n')
        _write(root, "pkg/thing.py", "def thing():\n    return 1\n")
        _write(root, "main.py", "from pkg import thing\n\nvalue = thing\n")

        deps = expand_dependencies(root, ["main.py"], max_depth=1)

        assert deps == ["pkg/__init__.py"]


def test_dependency_ordering_is_deterministic():
    """Repeated expansion yields identical ordering."""
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        runs = [expand_dependencies(root, ["auth_controller.py"], 3) for _ in range(5)]

        assert all(run == runs[0] for run in runs)


def test_duplicate_dependencies_removed():
    """A file reachable by two paths is reported exactly once."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "start.py", "from . import shared\n")
        _write(root, "shared.py", "def shared():\n    return 1\n")
        _write(root, "other.py", "from . import shared\n")

        deps = expand_dependencies(
            root, ["start.py", "other.py"], max_depth=1
        )

        assert deps == ["shared.py"]
        assert len(deps) == len(set(deps))


def test_cyclic_dependencies_protected():
    """An import cycle terminates and reports each file once."""
    with tempfile.TemporaryDirectory() as root:
        _make_cycle_repo(root)

        deps = expand_dependencies(root, ["a.py"], max_depth=5)

        assert sorted(deps) == ["b.py"]
        assert len(deps) == len(set(deps))


def test_self_import_terminates():
    """A file importing itself does not loop."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "loop.py", "from . import loop\n\nvalue = 1\n")

        deps = expand_dependencies(root, ["loop.py"], max_depth=5)

        assert deps == []


def test_unresolved_dependencies_ignored():
    """Imports naming modules that do not exist are simply dropped."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "main.py", "import nonexistent_module\nfrom . import also_missing\n")
        _write(root, "present.py", "def present():\n    return 1\n")
        _write(root, "main2.py", "from . import present\n")

        deps = expand_dependencies(root, ["main.py", "main2.py"], max_depth=2)

        assert deps == ["present.py"]


def test_external_and_stdlib_imports_not_traversed():
    """stdlib / third-party imports never resolve to repository files."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "main.py", "import os\nimport json\nimport requests\nfrom typing import List\n")

        assert expand_dependencies(root, ["main.py"], max_depth=3) == []


def test_dependency_expansion_rejects_negative_depth():
    """A negative max_depth yields no dependencies rather than looping."""
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        assert expand_dependencies(root, ["auth_controller.py"], max_depth=-1) == []


def test_seeds_are_excluded_from_dependencies():
    """A seed never reappears in its own dependency output."""
    with tempfile.TemporaryDirectory() as root:
        _write(root, "one.py", "from . import two\n")
        _write(root, "two.py", "from . import one\n")

        deps = expand_dependencies(root, ["one.py"], max_depth=3)

        assert deps == ["two.py"]
        assert "one.py" not in deps


# ---------------------------------------------------------------------------
# 9. Evidence pack
# ---------------------------------------------------------------------------


def test_evidence_pack_created_per_chunk():
    """One EvidenceItem is produced for each retrieved chunk, in the same order."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "all_three.py", "def alpha():\n    return 'alpha beta gamma'\n")
        _write(root, "one_only.py", "def alpha():\n    return 'alpha'\n")

        result = adapter.search(root, "alpha beta gamma", top_k=5)

        assert len(result.evidence) == len(result.chunks)
        for chunk, item in zip(result.chunks, result.evidence):
            assert item.chunk_id == chunk.chunk_id
            assert item.file_path == chunk.file_path
            assert item.line_start == chunk.line_start
            assert item.line_end == chunk.line_end
            assert item.source_type == EvidenceSourceType.RETRIEVED_CHUNK


def test_evidence_attribution_matches_chunk_exactly():
    """Evidence never invents a path or line number absent from the chunk."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "login", top_k=1)
        chunk = result.chunks[0]
        item = result.evidence[0]

        assert item.file_path == "auth.py"
        assert item.line_start == chunk.line_start == 1
        assert item.line_end == chunk.line_end
        assert item.chunk_id == chunk.chunk_id
        assert item.description == chunk.symbol


def test_evidence_empty_when_no_match():
    """No chunks means no evidence — never fabricated attribution."""
    adapter = RepositoryRetrievalAdapter()
    with tempfile.TemporaryDirectory() as root:
        _write(root, "auth.py", "def login(username, password):\n    return True\n")

        result = adapter.search(root, "zzzznotpresentzzzz", top_k=5)

        assert result.evidence == []


# ---------------------------------------------------------------------------
# 10. Full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_question_to_evidence():
    """question -> retrieval -> ranking -> dependencies -> evidence."""
    adapter = RepositoryRetrievalAdapter(max_depth=2)
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)
        _write(root, "unrelated.py", "def compute_totals(rows):\n    return sum(rows)\n")

        result = adapter.search(root, "authenticate", top_k=5)

        # Retrieval: the login chain was found, the unrelated file was not.
        paths = [c.file_path for c in result.chunks]
        assert "auth_controller.py" in paths
        assert "unrelated.py" not in paths

        # Ranking: descending relevance.
        scores = [c.relevance_score for c in result.chunks]
        assert scores == sorted(scores, reverse=True)
        assert all(s > 0.0 for s in scores)

        # Dependencies: proven hops only, in deterministic order.
        assert result.dependencies == ["auth_service.py", "jwt_service.py"]

        # Evidence: attribution for every chunk, nothing invented.
        assert len(result.evidence) == len(result.chunks)
        assert all(item.file_path in paths for item in result.evidence)

        # Contract echo.
        assert result.query == "authenticate"
        assert result.repository_path == root
        assert result.top_k == 5


def test_full_pipeline_is_repeatable():
    """The whole pipeline is stable across repeated invocations."""
    adapter = RepositoryRetrievalAdapter(max_depth=3)
    with tempfile.TemporaryDirectory() as root:
        _make_chain_repo(root)

        first = adapter.search(root, "login", top_k=5)
        second = adapter.search(root, "login", top_k=5)

        assert [c.chunk_id for c in first.chunks] == [c.chunk_id for c in second.chunks]
        assert first.dependencies == second.dependencies
        assert [e.chunk_id for e in first.evidence] == [e.chunk_id for e in second.evidence]


def test_invalid_repository_path_raises():
    """A non-existent repository surfaces the service's RuntimeError."""
    adapter = RepositoryRetrievalAdapter()

    with pytest.raises(RuntimeError):
        adapter.search("/definitely/not/a/real/path/xyz", "login", top_k=5)