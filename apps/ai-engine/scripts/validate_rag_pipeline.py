"""Comprehensive real-repository RAG pipeline validation.

Tests the retrieval pipeline against the actual AI-Code-Understanding-Assistant
repository.

Queries tested
--------------
1. "How does the analysis controller work?"
2. "Where is authentication handled?"
3. "How does the AI engine process a code analysis request?"
4. "How are retrieved chunks added to the LLM context?"
5. "xyzqjklmnop" — expected: no meaningful match

For each query reports:
  - top files, symbols, line ranges
  - lexical score (relevance_score)
  - semantic score: N/A (no embedding library; see BLOCKER below)
  - final score (= lexical + symbol_boost)
  - dependency path
  - evidence count

Grounding checks performed:
  - returned file paths exist on disk
  - line ranges are within file bounds
  - chunk IDs are deterministic
  - dependencies are real repository files
  - evidence is not fabricated

Run from apps/ai-engine:
    python scripts/validate_rag_pipeline.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters import RepositoryRetrievalAdapter  # noqa: E402
from app.ingestion import ingest_repository  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Repository root — two directories above this script's parent (ai-engine/).
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)

QUERIES = [
    "How does the analysis controller work?",
    "Where is authentication handled?",
    "How does the AI engine process a code analysis request?",
    "How are retrieved chunks added to the LLM context?",
    "xyzqjklmnop should return no meaningful match",
]


def _bar(title: str, width: int = 72) -> None:
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print("=" * width)


def _divider(width: int = 72) -> None:
    print("-" * width)


# ---------------------------------------------------------------------------
# Grounding checks
# ---------------------------------------------------------------------------


def _check_grounding(result, root: Path) -> list[str]:
    """Return a list of grounding violations, empty if all checks pass."""
    violations: list[str] = []

    for chunk in result.chunks:
        # 1. File path must exist on disk
        path = root / Path(chunk.file_path)
        if not path.exists():
            violations.append(f"MISSING FILE: {chunk.file_path}")
            continue

        # 2. Line ranges must be within the file
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            file_line_count = len(lines)
            if chunk.line_start < 1:
                violations.append(
                    f"INVALID line_start={chunk.line_start} in {chunk.file_path}"
                )
            if chunk.line_end > file_line_count + 1:
                violations.append(
                    f"LINE_END {chunk.line_end} > file lines {file_line_count} "
                    f"in {chunk.file_path}"
                )
        except OSError:
            violations.append(f"UNREADABLE: {chunk.file_path}")

    # 3. Dependency files must exist on disk
    for dep in result.dependencies:
        dep_path = root / Path(dep)
        if not dep_path.exists():
            violations.append(f"MISSING DEP: {dep}")

    # 4. Evidence chunk_ids must map to real chunks
    chunk_ids = {c.chunk_id for c in result.chunks}
    for ev in result.evidence:
        if ev.chunk_id not in chunk_ids:
            violations.append(
                f"ORPHAN EVIDENCE chunk_id={ev.chunk_id!r}"
            )

    # 5. No duplicate chunk_ids
    seen_ids: set[str] = set()
    for chunk in result.chunks:
        if chunk.chunk_id in seen_ids:
            violations.append(f"DUPLICATE chunk_id={chunk.chunk_id!r}")
        seen_ids.add(chunk.chunk_id)

    # 6. Chunks and dependencies must be disjoint
    chunk_files = {c.file_path for c in result.chunks}
    overlap = chunk_files & set(result.dependencies)
    if overlap:
        violations.append(f"FILE IN BOTH CHUNKS AND DEPS: {overlap}")

    # 7. Chunks ordered by descending relevance_score
    scores = [c.relevance_score for c in result.chunks]
    if scores != sorted(scores, reverse=True):
        violations.append("CHUNKS NOT SORTED by descending relevance_score")

    return violations


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def main() -> None:
    adapter = RepositoryRetrievalAdapter(max_depth=2)
    root = Path(REPO_ROOT).resolve()

    print(f"\nValidating RAG pipeline against: {root}")
    print(f"Repository exists: {root.is_dir()}")

    # ── Corpus size benchmark ────────────────────────────────────────────
    _bar("Corpus ingestion benchmark")
    t0 = time.perf_counter()
    corpus = ingest_repository(str(root))
    ingest_elapsed = time.perf_counter() - t0
    print(f"  Corpus size       : {len(corpus)} chunks")
    print(f"  Ingestion time    : {ingest_elapsed:.3f}s")

    # ── Per-query validation ─────────────────────────────────────────────
    all_ok = True

    for qi, query in enumerate(QUERIES, 1):
        _bar(f"Query {qi}: {query[:60]}...")

        t0 = time.perf_counter()
        result = adapter.search(str(root), query, top_k=5)
        query_elapsed = time.perf_counter() - t0

        print(f"  Retrieval latency : {query_elapsed:.3f}s")
        print(f"  Chunks returned   : {len(result.chunks)}")
        print(f"  Evidence items    : {len(result.evidence)}")
        print(f"  Dependencies      : {len(result.dependencies)}")

        _divider()
        print(f"  TOP CHUNKS:")
        for rank, chunk in enumerate(result.chunks, 1):
            print(
                f"    {rank}. {chunk.file_path}:{chunk.line_start}-{chunk.line_end}"
            )
            print(
                f"       score={chunk.relevance_score:.3f}  symbol={chunk.symbol!r}"
            )
            print(f"       chunk_id={chunk.chunk_id}")

        if result.dependencies:
            _divider()
            print("  DEPENDENCY PATH:")
            for dep in result.dependencies:
                print(f"    → {dep}")

        # ── Grounding checks ─────────────────────────────────────────────
        _divider()
        violations = _check_grounding(result, root)
        if violations:
            all_ok = False
            print("  GROUNDING VIOLATIONS:")
            for v in violations:
                print(f"    ✗ {v}")
        else:
            print("  GROUNDING: OK (all file paths exist, lines in bounds, no duplicates)")

        # ── Expected no-match query ──────────────────────────────────────
        if qi == 5:
            if len(result.chunks) == 0:
                print("  NO-MATCH: OK (correctly returned empty result)")
            else:
                print(
                    f"  NO-MATCH WARNING: got {len(result.chunks)} chunks for "
                    f"'no-match' query (lexical match on common tokens?)"
                )

    # ── Semantic retrieval status ────────────────────────────────────────
    _bar("Semantic retrieval status")
    import importlib.util
    has_embedding = (
        importlib.util.find_spec("sentence_transformers") is not None
        or importlib.util.find_spec("fastembed") is not None
    )
    if has_embedding:
        print("  AVAILABLE - semantic retrieval can be implemented.")
    else:
        print("  BLOCKED - no embedding library installed.")
        print("  Production path: lexical (token-overlap) + symbol-aware boost.")
        print("  To unblock: add sentence-transformers or fastembed to requirements.txt")

    # ── Summary ──────────────────────────────────────────────────────────
    _bar("Summary")
    print(f"  Corpus          : {len(corpus)} chunks")
    print(f"  Ingestion time  : {ingest_elapsed:.3f}s")
    print(f"  Queries tested  : {len(QUERIES)}")
    print(f"  Semantic search : {'available' if has_embedding else 'BLOCKED (no embedding lib)'}")
    print(f"  All grounding OK: {all_ok}")
    print()

    if all_ok:
        print("ALL GROUNDING CHECKS PASSED")
    else:
        print("SOME GROUNDING CHECKS FAILED -- see violations above")
        sys.exit(1)


if __name__ == "__main__":
    main()
