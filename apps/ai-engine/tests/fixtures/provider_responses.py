"""Deterministic stand-ins for live LLM output.

These strings replace a real model completion so that contract, grounding, and
confidence tests run in milliseconds and produce identical results on every
machine.  They are intentionally plain: no model was asked for anything, and
none of this text should be treated as an authoritative analysis.

Three of the constants are deliberately *wrong* in a specific way:

- ``DEPENDENCY_CLAIM_TEXT`` names a library that the accompanying snippet does
  **not** import.  It is used to prove that a textual model claim never becomes
  a structured dependency.
- ``WHITESPACE_TEXT`` is blank.  It is used to prove the fallback-summary path.
- ``UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT`` names downstream services that were
  never supplied.  It is used to prove that a relationship the caller never
  provided cannot become structured output.

``MALFORMED_BODY`` is not a string at all — it is the shape a provider returns
when its upstream JSON is unparseable, so the provider layer can be exercised
without a socket.
"""

from __future__ import annotations

EXPLANATION_TEXT = (
    "The function `add` takes two arguments and returns their sum. "
    "It performs no validation and no error handling."
)
"""Plausible, fully grounded explanation of ``SIMPLE_SOURCE``."""

STRUCTURE_TEXT = (
    "The module declares one top-level function, `add`, defined at line 1 "
    "with a single return statement on line 2."
)
"""Plausible, fully grounded structure summary of ``SIMPLE_SOURCE``."""

ERROR_EXPLANATION_TEXT = (
    "The call raises IndexError because `items[0]` is evaluated on an empty "
    "list. A length check before indexing would avoid the exception."
)
"""Plausible, grounded error explanation of ``ERROR_SOURCE``."""

IMPROVEMENT_TEXT = (
    "Guard against a zero divisor before dividing, and document the return "
    "type. Severity: medium, category: correctness."
)
"""Plausible, grounded improvement suggestion for ``IMPROVABLE_SOURCE``."""

DEPENDENCY_CLAIM_TEXT = (
    "This module depends on the requests library for HTTP access."
)
"""FABRICATED: ``DEPENDENCIES_SOURCE`` never imports ``requests``."""

WHITESPACE_TEXT = "   \n\t\n  "
"""Whitespace-only completion — triggers the deterministic fallback summary."""

MALFORMED_BODY: object = {"unexpected": ["shape", "without", "message"]}
"""A provider payload with no ``message.content`` key.

Represents a provider that answers HTTP 200 but returns JSON the provider layer
cannot read, e.g. ``{"unexpected": [...]}``.  Typed as ``object`` because it is
deliberately not an ``LLMResponse``.
"""

GIT_FACT_CLAIM_TEXT = (
    "This function was introduced in commit a1b2c3d by the platform team in "
    "PR #42, and is covered by three unit tests."
)
"""FABRICATED repository facts: commit hash, author team, PR number, test count.

Used to prove the engine never fabricates Git or test evidence, and that a
free-text answer carrying such claims is still reported as UNKNOWN confidence.
"""

UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT = (
    "This module is tightly coupled to the billing service and the "
    "notification worker, and changing it requires a coordinated release."
)
"""FABRICATED relationships: two named downstream services that were never
supplied, plus a release process that does not exist.

Used by the relationship/context scenario to prove that naming a system the
caller never mentioned produces no structured output and no evidence item.
"""

ONBOARDING_QUESTION_TEXT = (
    "I am new to this project. How do I get started, and what should I read "
    "first?"
)
"""A realistic new-developer question, used by the onboarding scenario.

The public API has no onboarding route, so this question is what a caller
actually sends — through the ordinary explanation analysis — to ask for it.
"""
