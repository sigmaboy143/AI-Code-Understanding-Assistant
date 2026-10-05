"""Concrete repository retrieval adapter (IRetrievalAdapter).

This module turns a natural-language question into a grounded, evidence-backed
``RetrievalResult`` using only what the repository can prove:

    question
      -> lexical chunk retrieval      (app.retrieval.service.search)
      -> ranking                      (existing relevance_score, untouched)
      -> dependency expansion         (repository-proven internal imports)
      -> evidence pack                (app.evidence.models.EvidenceItem)
      -> RetrievalResult

Design constraints
------------------
- **No fabrication.**  File paths, symbols, line ranges, chunk ids, and
  dependency paths are only ever reported when they are read out of real
  repository files.  An import that cannot be resolved to a file on disk stays
  unresolved and is simply omitted.
- **No new infrastructure.**  Retrieval, chunking, and symbol extraction are
  reused from ``app.retrieval`` and ``app.ingestion``.  This module owns no
  corpus and no second index; it only reads individual files, bounded by
  ``max_depth``.
- **Deterministic.**  Breadth-first over sorted candidate targets, so the same
  question against the same repository always yields the same dependency order.
- **Provider-agnostic.**  No embedding service, no vector database, no LLM call.

Grounding rules
---------------
Every field in the returned result traces to one of two places:

1. ``RetrievedChunk`` — produced by the ingestion/retrieval pipeline.
2. ``EvidenceItem`` — an attribution record derived one-to-one from a chunk.

Code content lives on ``RetrievalResult.chunks`` only.  ``EvidenceItem`` has no
content field by design, so none is invented here.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.models import EvidenceItem, EvidenceSourceType
from app.retrieval.base import RetrievedChunk
from app.retrieval.service import search as _search

# Default bound on how many import hops are followed from a retrieved file.
# Depth 2 means: retrieved file -> its internal import -> that file's import.
DEFAULT_MAX_DEPTH = 2

# Candidate module suffixes tried when resolving a dotted module path to a
# real file.  Both forms are valid Python targets.
_MODULE_SUFFIXES = (".py", "/__init__.py")


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class RetrievalResult(BaseModel):
    """Grounded result of one repository retrieval.

    Follows the repository's Pydantic conventions: ``extra="forbid"`` so a
    caller cannot smuggle unvalidated extra claims into the result.

    Attributes
    ----------
    chunks:
        Ranked chunks, highest ``relevance_score`` first.  Carries the actual
        code content.  Empty when the question matches nothing.
    evidence:
        One ``EvidenceItem`` per chunk, preserving attribution.  Same length
        and order as ``chunks``.
    dependencies:
        Repository-proven internal dependency files, breadth-first from the
        retrieved files, deduplicated.  Empty when nothing resolves.
    repository_path:
        Repository root that was searched.
    query:
        The original question, echoed verbatim.
    top_k:
        Maximum number of chunks requested.
    """

    model_config = ConfigDict(extra="forbid")

    chunks: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Ranked retrieved chunks carrying the actual code content.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Attribution record for each retrieved chunk, same order.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Repository-proven internal dependency files, deduplicated.",
    )
    repository_path: str | None = Field(
        default=None,
        description="Repository root that was searched.",
    )
    query: str | None = Field(
        default=None,
        description="The original user question.",
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of chunks requested.",
    )


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class IRetrievalAdapter(ABC):
    """Contract every retrieval adapter must satisfy.

    Mirrors the convention already used by ``app.retrieval.base.RetrieverBase``:
    an ``ABC`` with a single ``@abstractmethod``.  A retrieval backend only has
    to satisfy this one method to be usable by the rest of the system.

    Usage::

        adapter: IRetrievalAdapter = RepositoryRetrievalAdapter()
        result = adapter.search("/path/to/repo", "how does login work", top_k=5)
        result.chunks        # list[RetrievedChunk] — actual code
        result.evidence      # list[EvidenceItem]  — attribution
        result.dependencies  # list[str]          — proven internal imports
    """

    @abstractmethod
    def search(
        self,
        repository_path: str,
        query: str,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Return the *top_k* most relevant chunks for *query*.

        Parameters
        ----------
        repository_path:
            Absolute or relative path to the repository root.
        query:
            Free-text question in the user's own words.
        top_k:
            Maximum number of chunks to return.

        Returns
        -------
        RetrievalResult
            Ranked chunks, matching evidence, and proven dependencies.
            A valid result with empty lists when nothing matches.
        """


# ---------------------------------------------------------------------------
# Import resolution helpers
# ---------------------------------------------------------------------------


def _package_parts(rel_path: str) -> list[str]:
    """Return the dotted package parts that contain *rel_path*.

    ``pkg/sub/mod.py`` -> ``["pkg", "sub"]``.  A top-level ``mod.py`` yields an
    empty list, which is correct: top-level modules have no package parent.
    """
    return PurePosixPath(rel_path).parent.parts


def _import_base_parts(rel_path: str, level: int) -> list[str]:
    """Return the package parts a relative import of *level* resolves against.

    ``level`` is Python's own dot count, so ``from .x import y`` is level 1
    (the current package), ``from ..x import y`` is level 2 (its parent), and so
    on.  Walking off the top of the tree yields an empty base, which lets
    ``from ...models import X`` resolve against the repository root.
    """
    package = _package_parts(rel_path)
    ascend = level - 1
    if ascend >= len(package):
        return []
    return list(package[: len(package) - ascend])


def _candidate_paths(module_parts: list[str]) -> list[str]:
    """Return the repository-relative files a dotted module could refer to.

    Only the two shapes Python actually resolves are considered:
    ``a/b/c.py`` and the package entry point ``a/b/c/__init__.py``.  Nothing is
    invented — the caller keeps a candidate only if it exists on disk.
    """
    if not module_parts:
        return []
    base = PurePosixPath(*module_parts).as_posix()
    return [f"{base}{suffix}" for suffix in _MODULE_SUFFIXES]


def _resolve_relative_import(
    importer_rel_path: str,
    node: ast.ImportFrom,
    root: Path,
) -> list[str]:
    """Resolve one relative ``ImportFrom`` to existing repository files.

    Handles ``from .auth import login`` and ``from ..services.user import
    UserService``.  The dotted *module* is what identifies the file; the
    imported names are symbols within it, not targets.
    """
    module_parts = node.module.split(".") if node.module else []
    if not module_parts:
        # ``from . import helpers`` — the imported name is the submodule.
        module_parts = [alias.name for alias in node.names]

    base = _import_base_parts(importer_rel_path, node.level)
    candidates = _candidate_paths([*base, *module_parts])

    resolved: list[str] = []
    for candidate in candidates:
        # Guard against escaping the repository root via ``..``-heavy imports.
        if candidate.startswith(".."):
            continue
        if (root / candidate).is_file():
            resolved.append(candidate)
    return resolved


def _resolve_dotted_module(module: str, root: Path) -> list[str]:
    """Resolve a dotted module path only if it names a real repository file.

    This is what separates a genuine internal import from ``os`` or ``json``:
    standard-library and third-party modules simply have no matching file under
    the repository root, so they are dropped rather than traversed.
    """
    if not module:
        return []
    candidates = _candidate_paths(module.split("."))
    return [c for c in candidates if (root / c).is_file()]


def _resolve_absolute_import(
    node: ast.ImportFrom,
    root: Path,
) -> list[str]:
    """Resolve a non-relative ``from <module> import <name>`` statement."""
    if not node.module:
        return []
    return _resolve_dotted_module(node.module, root)


def _read_text(path: Path) -> str | None:
    """Read *path* as UTF-8, replacing undecodable bytes.  ``None`` on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _internal_imports_of(rel_path: str, content: str, root: Path) -> list[str]:
    """Return every existing repository file that *rel_path* imports internally.

    Both import forms are handled:

    - ``import a.b``  /  ``import a.b as c``      — bare ``ast.Import``
    - ``from .a import b``                        — relative ``ast.ImportFrom``
    - ``from ..a.b import C``                     — dotted ``ast.ImportFrom``
    - ``from . import helper``                     — submodule ``ast.ImportFrom``

    Unparseable files and unresolvable imports contribute nothing.  Results are
    sorted so traversal order never depends on dict or filesystem ordering.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # Each alias carries its own dotted path: ``import a.b, c.d``.
            for alias in node.names:
                targets.update(_resolve_dotted_module(alias.name, root))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                targets.update(_resolve_relative_import(rel_path, node, root))
            else:
                targets.update(_resolve_absolute_import(node, root))

    return sorted(targets)


# ---------------------------------------------------------------------------
# Breadth-first expansion
# ---------------------------------------------------------------------------


def expand_dependencies(
    root_path: str,
    seed_files: list[str],
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[str]:
    """Expand *seed_files* into their proven internal dependency files.

    Algorithm — breadth-first, deterministic, cycle-safe:

    1. Seed a queue with ``(file, depth=0)`` in the order the caller supplied
       (i.e. retrieval rank order).
    2. Pop the oldest entry.  Skip if already expanded (``visited``).
    3. If ``depth == max_depth``, stop descending from this file — the bound is
       on hops away from a retrieved file, not on total work.
    4. Read the file, parse its imports, and resolve each to an existing file.
    5. Skip any target already in ``seen`` — this removes duplicates *and*
       breaks cycles, since a file that was emitted is never emitted again.
    6. Emit the target and enqueue it at ``depth + 1``.

    Guarantees
    ----------
    - **Deterministic** — queue order plus sorted import targets.
    - **No duplicates** — enforced by ``seen``.
    - **Cycle-safe** — enforced by ``seen`` and ``visited``.
    - **Bounded** — enforced by ``max_depth``.
    - **No fabrication** — every emitted path passed ``is_file()``.
    - **No external traversal** — stdlib and third-party modules never match a
      file under the repository root, so they are never enqueued.

    Parameters
    ----------
    root_path:
        Repository root.
    seed_files:
        Repository-relative files to expand from, in priority order.
    max_depth:
        Maximum number of import hops to follow from a seed.

    Returns
    -------
    list[str]
        Dependency files excluding the seeds themselves, in visit order.
    """
    if max_depth < 0:
        return []

    root = Path(root_path).resolve()
    seen: set[str] = set(seed_files)
    visited: set[str] = set()
    ordered: list[str] = []

    queue: deque[tuple[str, int]] = deque((f, 0) for f in seed_files)
    while queue:
        current, depth = queue.popleft()

        if current in visited:
            continue
        visited.add(current)

        if depth >= max_depth:
            continue

        content = _read_text(root / current)
        if content is None:
            continue

        for target in _internal_imports_of(current, content, root):
            if target in seen:
                continue
            seen.add(target)
            ordered.append(target)
            queue.append((target, depth + 1))

    return ordered


# ---------------------------------------------------------------------------
# Concrete adapter
# ---------------------------------------------------------------------------


class RepositoryRetrievalAdapter(IRetrievalAdapter):
    """Retrieval adapter over a filesystem repository.

    Composes the existing pipeline without duplicating any of it: lexical
    retrieval comes from ``app.retrieval.service``, import facts come from the
    repository source itself, and evidence records reuse
    ``app.evidence.models.EvidenceItem``.

    Parameters
    ----------
    max_depth:
        Maximum number of internal import hops to follow from a retrieved file.
        Defaults to :data:`DEFAULT_MAX_DEPTH`.

    Notes
    -----
    Instances hold no state and are safe to share.  Ingestion is delegated to
    ``app.retrieval.service.search``, which already performs the cached
    ``ingest`` call, so this adapter indexes nothing itself.
    """

    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        self._max_depth = max_depth

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        repository_path: str,
        query: str,
        top_k: int = 5,
    ) -> RetrievalResult:
        """See :meth:`IRetrievalAdapter.search`."""
        # ``service.search`` ingests on demand and caches per absolute path, so
        # this single call covers both indexing and retrieval.  A blank query
        # short-circuits to a valid empty result without touching the index.
        if not query or not query.strip():
            return RetrievalResult(
                chunks=[],
                evidence=[],
                dependencies=[],
                repository_path=repository_path,
                query=query,
                top_k=top_k,
            )

        chunks: list[RetrievedChunk] = _search(repository_path, query, top_k=top_k)

        # Expand from the retrieved files in rank order, deduplicated, so the
        # most relevant file's dependencies are discovered first.
        seed_files: list[str] = []
        seen_files: set[str] = set()
        for chunk in chunks:
            if chunk.file_path not in seen_files:
                seen_files.add(chunk.file_path)
                seed_files.append(chunk.file_path)

        dependencies = expand_dependencies(
            repository_path,
            seed_files,
            max_depth=self._max_depth,
        )

        evidence = [
            EvidenceItem(
                source_type=EvidenceSourceType.RETRIEVED_CHUNK,
                file_path=chunk.file_path,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                chunk_id=chunk.chunk_id,
                # When no symbol is available fall back to the file path for
                # a human-readable description rather than the raw source_type
                # string.  This keeps descriptions grounded and informative.
                description=chunk.symbol or chunk.file_path,
            )
            for chunk in chunks
        ]

        return RetrievalResult(
            chunks=chunks,
            evidence=evidence,
            dependencies=dependencies,
            repository_path=repository_path,
            query=query,
            top_k=top_k,
        )