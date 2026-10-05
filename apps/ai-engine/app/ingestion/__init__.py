"""Repository ingestion pipeline.

Produces ``RetrievedChunk`` objects from a filesystem repository,
feeding the existing retrieval layer (Task 7) and context builder (Task 8).

Usage::

    from app.ingestion import ingest_repository
    chunks = ingest_repository("/path/to/repo", max_chars_per_chunk=800)
    retriever = InMemoryRetriever(corpus=chunks)
    results = retriever.retrieve("login authentication", top_k=5)
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Sequence

from app.evidence.models import EvidenceSourceType
from app.retrieval.base import RetrievedChunk
from app.schemas.code_understanding import ProgrammingLanguage

# Import symbol extraction (new module, Task 7 extension)
from app.ingestion.symbols import extract_symbols


# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------

_EXT_TO_LANGUAGE: dict[str, ProgrammingLanguage] = {
    ".py": ProgrammingLanguage.PYTHON,
    ".ts": ProgrammingLanguage.TYPESCRIPT,
    ".tsx": ProgrammingLanguage.TYPESCRIPT,
    ".js": ProgrammingLanguage.JAVASCRIPT,
    ".jsx": ProgrammingLanguage.JAVASCRIPT,
    ".java": ProgrammingLanguage.JAVA,
    ".go": ProgrammingLanguage.GO,
    ".rs": ProgrammingLanguage.RUST,
    ".cpp": ProgrammingLanguage.CPP,
    ".c": ProgrammingLanguage.C,
    ".h": ProgrammingLanguage.CPP,
    ".hpp": ProgrammingLanguage.CPP,
    ".cs": ProgrammingLanguage.CSHARP,
    ".go": ProgrammingLanguage.GO,
}

_IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    "out",
    "build",
    "coverage",
    ".venv",
    "venv",
    ".pytest_cache",
    "webview-ui/node_modules",
}

_IGNORED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".dockerignore",
    ".env.example",
    ".pytest_cache",
}


def _is_binary_file(filepath: Path) -> bool:
    """Heuristic: treat files with binary mime types as binary."""
    mime, _ = mimetypes.guess_type(filepath.name)
    if mime and mime.startswith("image/"):
        return True
    if mime and mime.startswith("application/"):
        # Allow text-y applications
        if not mime.startswith("application/x-"):
            return True
    return False


def _should_ignore_path(filepath: Path, root: Path) -> bool:
    """Return True if *filepath* (relative to *root*) should be ignored."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        return True

    parts = rel.parts
    for part in parts:
        if part in _IGNORED_DIR_NAMES:
            return True

    if filepath.suffix.lower() in _IGNORED_EXTENSIONS:
        return True

    return False


def _detect_language(extension: str) -> ProgrammingLanguage:
    """Detect programming language from file extension."""
    return _EXT_TO_LANGUAGE.get(extension, ProgrammingLanguage.OTHER)


# ---------------------------------------------------------------------------
# Chunk ID generation
# ---------------------------------------------------------------------------

import hashlib


def _chunk_id(file_path: str, chunk_index: int) -> str:
    """Deterministic stable chunk ID based on file path and chunk index."""
    hash_input = f"{file_path}:{chunk_index}".encode("utf-8")
    return hashlib.sha256(hash_input).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Original chunk generator (unchanged)
# ---------------------------------------------------------------------------

def _create_chunks(
    file_path: str,
    content: str,
    language: ProgrammingLanguage,
    max_chars_per_chunk: int = 800,
) -> list[RetrievedChunk]:
    """Split *content* into ``RetrievedChunk`` objects of reasonable size.

    Chunks preserve exact source text and line numbers.  Chunk IDs are
    deterministic (hash of file_path + index).
    """
    if not content.strip():
        return []

    lines = content.splitlines(keepends=True)
    chunks: list[RetrievedChunk] = []

    char_pos = 0
    chunk_index = 0

    while char_pos < len(content):
        end = min(char_pos + max_chars_per_chunk, len(content))

        if end < len(content):
            search_start = max(char_pos, end - 200)
            nearest_break = content.rfind("\n", search_start, end)
            if nearest_break >= search_start:
                end = nearest_break + 1

        chunk_content = content[char_pos:end]

        preceding_content = content[:char_pos]
        line_start = preceding_content.count("\n") + 1 if char_pos > 0 else 1
        chunk_lines = chunk_content.split("\n")
        line_end = line_start + len(chunk_lines) - 1
        if chunk_content.endswith("\n"):
            line_end = line_start + len(chunk_lines) - 1
        else:
            line_end = line_start + len(chunk_lines) - 1

        line_start_pos = content[:char_pos].count("\n") + 1 if char_pos > 0 else 1
        end_pos = char_pos + len(chunk_content)
        line_end_pos = content[:end_pos].count("\n") + 1

        chunk_id = _chunk_id(file_path, chunk_index)

        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                content=chunk_content,
                line_start=line_start_pos,
                line_end=line_end_pos,
                source_type=EvidenceSourceType.SOURCE_CODE,
                relevance_score=0.0,
            )
        )

        char_pos = end
        chunk_index += 1

    return chunks


# ---------------------------------------------------------------------------
# Symbol assignment (post-processing step)
# ---------------------------------------------------------------------------

def _assign_chunk_symbols(
    chunks: list[RetrievedChunk],
    content: str,
    language: ProgrammingLanguage,
) -> list[RetrievedChunk]:
    """Assign ``RetrievedChunk.symbol`` based on extracted symbols.

    For each chunk, if any extracted symbol's line range falls within the
    chunk's ``line_start``–``line_end`` interval, the chunk receives that
    symbol string.  If multiple symbols overlap, the first one wins.

    Parameters
    ----------
    chunks:
        The chunk list returned by ``_create_chunks``.
    content:
        The full source file content (used for symbol line numbers).
    language:
        The ``ProgrammingLanguage`` of the source file.

    Returns
    -------
    list[RetrievedChunk]
        Chunks with ``symbol`` fields populated where applicable.
    """
    # Extract all symbols for the file; each returns a list of strings.
    # We also need line numbers, so we re-extract using a helper that tracks them.
    from app.ingestion.symbols import _extract_python_symbols, _extract_js_symbols

    file_symbols: list[dict] = []
    if language == ProgrammingLanguage.PYTHON:
        file_symbols = _extract_python_symbols(content)
    else:
        file_symbols = _extract_js_symbols(content, language)

    # Build a mapping: line_start -> symbol string
    # The extraction functions return dicts with ``line_start``/``line_end``.
    line_to_symbol: dict[int, str] = {}
    for s in file_symbols:
        ln = s.get("line_start")
        if ln is not None:
            # Use the first symbol at each line
            if ln not in line_to_symbol:
                # Format the symbol string for display
                sym = s["name"]
                if s.get("is_constructor"):
                    # Constructor: the symbol will be the class name, set by caller
                    continue
                if s.get("async"):
                    sym = f"async {sym}"
                line_to_symbol[ln] = sym

    # Now assign symbols to chunks
    for chunk in chunks:
        sym = None
        # Check if any symbol line falls within this chunk's range
        for line_no, sym_str in line_to_symbol.items():
            if chunk.line_start <= line_no <= chunk.line_end:
                sym = sym_str
                break
        # Also check the chunk's last line
        if sym is None and chunk.line_end >= chunk.line_start:
            last_line = chunk.line_end
            for line_no, sym_str in line_to_symbol.items():
                if chunk.line_start <= line_no <= last_line:
                    sym = sym_str
                    break
        chunk.symbol = sym

    return chunks


# ---------------------------------------------------------------------------
# Repository scanner
# ---------------------------------------------------------------------------

def scan_repository(root_path: str) -> dict[str, list[str]]:
    """Walk *root_path* and return a mapping of file_path → content for all
    source files that should be ingested.

    Returns a dict where keys are repository-relative file paths and values
    are the file contents.  Ignored directories and binary files are skipped.
    """
    root = Path(root_path).resolve()
    result: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _IGNORED_DIR_NAMES
        )

        dirpath = Path(dirpath)
        for filename in sorted(filenames):
            filepath = dirpath / filename

            if _should_ignore_path(filepath, root):
                continue

            if _is_binary_file(filepath):
                continue

            ext = filepath.suffix.lower()
            if ext not in _EXT_TO_LANGUAGE:
                continue

            try:
                # Always use POSIX-style forward slashes in rel_path so that
                # downstream consumers (dependency expansion, chunk_id hashing,
                # evidence attribution) produce identical paths on all platforms.
                rel_path = filepath.relative_to(root).as_posix()
                content = filepath.read_text(encoding="utf-8", errors="replace")
                result[rel_path] = content
            except (OSError, UnicodeDecodeError):
                continue

    return result


# ---------------------------------------------------------------------------
# Main ingestion entry point
# ---------------------------------------------------------------------------

def ingest_repository(
    root_path: str,
    max_chars_per_chunk: int = 800,
) -> list[RetrievedChunk]:
    """Ingest an entire repository into a list of ``RetrievedChunk`` objects.

    Parameters
    ----------
    root_path:
        Absolute or repository-relative path to scan.
    max_chars_per_chunk:
        Maximum characters per chunk.  Keeps chunks small enough for
        effective retrieval.

    Returns
    -------
    list[RetrievedChunk]
        A flat list of chunks representing the repository corpus.
        Duplicates (same chunk_id) are deduplicated by the caller if desired.
    """
    root = Path(root_path).resolve()
    if not root.is_dir():
        return []

    # Step 1: Scan and collect source files
    file_contents = scan_repository(str(root))

    # Step 2: Parse each file and generate chunks
    all_chunks: list[RetrievedChunk] = []

    for rel_path, content in file_contents.items():
        # Detect language from extension
        ext = Path(rel_path).suffix.lower()
        language = _detect_language(ext)

        # Generate chunks
        chunks = _create_chunks(rel_path, content, language, max_chars_per_chunk)

        # Step 2b: Assign symbols (post-processing)
        chunks = _assign_chunk_symbols(chunks, content, language)

        all_chunks.extend(chunks)

    return all_chunks