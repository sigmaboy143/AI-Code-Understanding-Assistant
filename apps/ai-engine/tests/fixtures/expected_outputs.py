"""Hand-written expectations used by the evaluation layer.

These constants encode what the AI Engine is *supposed* to do, written down
independently of the implementation so that an evaluation test comparing the
two is a genuine check rather than a restatement of the code.

They are deliberately conservative.  Where the engine's documented behaviour is
"say you do not know", the expectation encodes UNKNOWN, not a best guess.
"""

from __future__ import annotations

from app.evidence.models import ConfidenceLevel, EvidenceSourceType

# ---------------------------------------------------------------------------
# Confidence expectations
# ---------------------------------------------------------------------------

EXPECTED_UNKNOWN_LEVEL = ConfidenceLevel.UNKNOWN
"""Free-text LLM answers are never claim-mapped to evidence, so the whole-response
confidence must be UNKNOWN even when source code or retrieved chunks were
supplied.  The evidence list still records what was available."""

EXPECTED_CONFIRMED_LEVEL = ConfidenceLevel.CONFIRMED
"""Used only for structured claims that are directly established by supplied
evidence — currently the deterministic dependency extraction, never the
free-text summary."""

EXPECTED_INFERRED_LEVEL = ConfidenceLevel.INFERRED
"""Used when a conclusion is reasoned from evidence but not explicitly
established.  The orchestrator's free-text path does not produce this level;
it is asserted here to keep the three-state vocabulary honest and exhaustive."""

CONFIDENCE_LEVELS = (
    ConfidenceLevel.CONFIRMED,
    ConfidenceLevel.INFERRED,
    ConfidenceLevel.UNKNOWN,
)
"""The complete, closed set of confidence levels.  Exactly three by contract."""

# ---------------------------------------------------------------------------
# Dependency expectations
# ---------------------------------------------------------------------------

EXPECTED_GROUNDED_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("math", "standard_library"),
    ("pathlib", "standard_library"),
)
"""Dependencies that ``DEPENDENCIES_SOURCE`` genuinely imports, in first-seen
order, as ``(name, kind)`` string pairs so the expectation is JSON-visible."""

EXPECTED_UNGROUNDED_DEPENDENCIES: tuple[str, ...] = (
    "requests",
    "numpy",
    "pandas",
    "torch",
    "flask",
)
"""Libraries the snippet never imports.  None may ever appear as a structured
dependency, no matter what the model claims in free text."""

# ---------------------------------------------------------------------------
# Evidence expectations
# ---------------------------------------------------------------------------

RESERVED_EVIDENCE_SOURCE_TYPES: tuple[EvidenceSourceType, ...] = (
    EvidenceSourceType.TEST,
    EvidenceSourceType.GIT_COMMIT,
)
"""Source types the contract defines but the engine must never auto-populate.
Fabricating either is a hard failure, so evaluation asserts their absence."""

PRODUCIBLE_EVIDENCE_SOURCE_TYPES: tuple[EvidenceSourceType, ...] = (
    EvidenceSourceType.SOURCE_CODE,
    EvidenceSourceType.RETRIEVED_CHUNK,
    EvidenceSourceType.FILE,
    EvidenceSourceType.DOCUMENTATION,
)
"""Source types the engine may legitimately emit on the paths under test."""

# ---------------------------------------------------------------------------
# Fabrication expectations
# ---------------------------------------------------------------------------

FABRICATED_REPOSITORY_FACTS: tuple[str, ...] = (
    "a1b2c3d",
    "PR #42",
    "commit a1b2c3d",
    "platform team",
    "three unit tests",
)
"""Repository facts that are NOT present in any supplied fixture.

The evaluation layer asserts that none of these strings reaches any
*structured* field of the response.  A model is free to hallucinate them in
free text — that is precisely why the whole-response confidence stays UNKNOWN —
but the engine must never promote such a claim into a dependency, an evidence
item, or a confidence upgrade.
"""
