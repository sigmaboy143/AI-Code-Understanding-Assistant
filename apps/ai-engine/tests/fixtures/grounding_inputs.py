"""Synthetic retrieved context used to exercise evidence grounding.

Chunks are the only way a caller can inject supplementary code into a request
without touching ``source_code``.  They also drive the ``evidence`` list on the
response, so they are the fixture of choice for any test that asks "is this
claim traceable to something that was actually supplied?".

All paths are synthetic (``src/``, ``tests/``) and all content is trivial.
"""

from __future__ import annotations

from app.retrieval.base import RetrievedChunk

INTERNAL_CHUNK = RetrievedChunk(
    chunk_id="fixture-internal-helpers",
    file_path="src/helpers.py",
    symbol="clamp",
    content=(
        "def clamp(value, low, high):\n"
        "    return max(low, min(high, value))\n"
    ),
    line_start=1,
    line_end=2,
    relevance_score=0.9,
    source_type="source_code",
)
"""A high-relevance internal chunk.  Its ``chunk_id`` and line range must be
preserved verbatim in any evidence item derived from it."""

EXTERNAL_CHUNK = RetrievedChunk(
    chunk_id="fixture-external-config",
    file_path="src/config_loader.py",
    symbol="load_settings",
    content=(
        "import json\n"
        "\n"
        "def load_settings(path):\n"
        "    with open(path) as handle:\n"
        "        return json.load(handle)\n"
    ),
    line_start=1,
    line_end=5,
    relevance_score=0.5,
    source_type="source_code",
)
"""A lower-relevance chunk that also contains a standard-library import, so a
dependency-grounding test can prove chunk evidence contributes to the grounded
dependency list."""

MALFORMED_CHUNK_CONTENT = "this is not valid python ((( \n"
"""Deliberately unparseable text supplied as supplementary evidence.

The dependency extractor must ignore it rather than guess, so an empty or
unchanged dependency list is the correct outcome.
"""


def chunk_list(*chunks: RetrievedChunk) -> list[RetrievedChunk]:
    """Return *chunks* as a list, for the ``retrieved_chunks`` parameter.

    Accepts varargs so a test can pass a single chunk without writing a list
    literal, and a pair when it needs to assert relevance ordering.
    """
    return list(chunks)
