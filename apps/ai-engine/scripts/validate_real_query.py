"""Step 7 real-repository validation: query the actual ai-engine codebase.

Run from apps/ai-engine:
    python scripts/validate_real_query.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script from apps/ai-engine without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters import RepositoryRetrievalAdapter  # noqa: E402


def main() -> None:
    adapter = RepositoryRetrievalAdapter(max_depth=2)
    result = adapter.search(".", "How does the analysis controller work?", top_k=5)

    print("=" * 72)
    print(f"query  : {result.query}")
    print(f"repo   : {result.repository_path}")
    print(f"top_k  : {result.top_k}")
    print("=" * 72)

    print(f"\nCHUNKS ({len(result.chunks)})")
    print("-" * 72)
    for rank, chunk in enumerate(result.chunks, 1):
        print(
            f"{rank}. {chunk.file_path}:{chunk.line_start}-{chunk.line_end} "
            f"score={chunk.relevance_score:.3f} symbol={chunk.symbol!r}"
        )
        print(f"   id={chunk.chunk_id}")

    print(f"\nDEPENDENCIES ({len(result.dependencies)})")
    print("-" * 72)
    for dep in result.dependencies:
        print(f"  {dep}")

    print(f"\nEVIDENCE ({len(result.evidence)})")
    print("-" * 72)
    for item in result.evidence:
        print(
            f"  {item.source_type.value} {item.file_path}:{item.line_start}"
            f"-{item.line_end} desc={item.description!r}"
        )

    print("\nGROUNDING CHECKS")
    print("-" * 72)
    assert len(result.evidence) == len(result.chunks), "evidence/chunk mismatch"
    print("  OK  one evidence item per chunk, same length")

    chunk_files = {c.file_path for c in result.chunks}
    overlap = chunk_files & set(result.dependencies)
    assert not overlap, f"file reported as both chunk and dependency: {overlap}"
    print("  OK  chunks and dependencies are disjoint")

    for dep in result.dependencies:
        assert dep not in chunk_files
    print("  OK  no duplicate file reporting")

    assert result.chunks == sorted(
        result.chunks, key=lambda c: c.relevance_score, reverse=True
    )
    print("  OK  chunks ordered by descending relevance")

    for chunk in result.chunks:
        assert chunk.file_path and chunk.chunk_id and chunk.line_start >= 1
    print("  OK  every chunk carries file_path, chunk_id, line_start")

    print("\nALL GROUNDING CHECKS PASSED")


if __name__ == "__main__":
    main()