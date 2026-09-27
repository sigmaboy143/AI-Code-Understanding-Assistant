"""LLM output validation and normalisation pipeline (Task 10).

Pipeline
--------
LLM output
    ↓
Parse (extract content string from LLMResponse)
    ↓
Validate (detect empty / malformed content)
    ↓
Normalise (safe whitespace normalisation)
    ↓
Evidence / confidence determination
    ↓
Return validated tuple: (summary_text, confidence)

Design principles
-----------------
- Do NOT trust raw LLM output.
- Detect and reject empty or whitespace-only content.
- Never silently convert malformed output into fabricated data.
- Return a deterministic fallback when the response is unusable.
- Do not expose provider secrets, stack traces, or internal details.
- Log only safe diagnostic information (content length, provider name).
- Keep the existing ``ProviderError`` propagation contract unchanged.

Confidence semantics
--------------------
The free-text LLM response is a whole-response answer; individual model
claims are not mapped to evidence items.  Therefore:

- The response-level ``ConfidenceLevel`` is always **UNKNOWN** for
  free-text paths.  Available evidence (source code, retrieved chunks) is
  recorded in the ``evidence`` list so callers can inspect what the model
  had access to, but that availability does NOT confirm the correctness of
  the model's statements.
- ``CONFIRMED`` is only appropriate when a specific structured claim has
  been directly verified against an evidence item.  This pipeline does not
  perform that mapping.
- No numeric confidence score is computed.

Current limitations
-------------------
- The provider currently returns free-text, not structured JSON.  There is
  no JSON extraction or parsing in this pipeline.  Structured fields in
  ``CodeUnderstandingResponse`` remain null / empty until structured output
  is implemented in the provider.
- Claim-level evidence mapping is not implemented.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.evidence.models import ConfidenceLevel, ResponseConfidence
from app.providers.base import LLMResponse

if TYPE_CHECKING:
    from app.context_builder.builder import IncludedChunk

logger = logging.getLogger(__name__)

# Fallback summary used when the provider returns no usable content.
_FALLBACK_SUMMARY = "No summary produced by provider."

# Maximum characters kept from the normalised LLM output.
# Prevents oversized summaries from reaching the response model.
_MAX_SUMMARY_CHARS = 10_000


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class OutputValidationError(Exception):
    """Raised by the validator when a response cannot be normalised at all.

    This exception is intentionally separate from ``ProviderError`` so
    callers can distinguish a bad *response* from a provider *failure*.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_llm_response(
    llm_response: LLMResponse,
    included_chunks: list["IncludedChunk"] | None = None,
    file_path: str | None = None,
) -> tuple[str, ResponseConfidence]:
    """Validate and normalise a raw ``LLMResponse``.

    Parameters
    ----------
    llm_response:
        The raw response returned by the LLM provider.
    included_chunks:
        Optional list of ``IncludedChunk`` objects that were included in
        the prompt context.  Used to derive the confidence level.
    file_path:
        Repository-relative path from the original request.  Used for
        evidence attribution when no chunks are available.

    Returns
    -------
    tuple[str, ResponseConfidence]
        ``(summary_text, confidence)`` where ``summary_text`` is a safe,
        normalised, non-empty string and ``confidence`` reflects the
        evidence available.

    Notes
    -----
    - Never raises for a malformed / empty response — returns a fallback
      summary and UNKNOWN confidence instead.
    - Never exposes provider secrets or stack traces in the returned values.
    """
    # ── Step 1: Extract raw content ──────────────────────────────────────
    raw_content = _extract_content(llm_response)

    # ── Step 2: Normalise whitespace ─────────────────────────────────────
    normalised = _normalise_whitespace(raw_content)

    # ── Step 3: Validate — detect empty / malformed content ─────────────
    if not normalised:
        logger.warning(
            "Provider returned empty or whitespace-only content (model=%s, finish_reason=%s).",
            llm_response.model or "unknown",
            llm_response.finish_reason or "unknown",
        )
        summary_text = _FALLBACK_SUMMARY
    else:
        summary_text = _truncate(normalised, _MAX_SUMMARY_CHARS)

    # ── Step 4: Evidence / confidence determination ───────────────────────
    confidence = _determine_confidence(included_chunks, file_path)

    return summary_text, confidence


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_content(llm_response: LLMResponse) -> str:
    """Extract the content string from an ``LLMResponse``.

    Returns an empty string if ``content`` is missing or not a string.
    Never raises.
    """
    try:
        content = llm_response.content
        if not isinstance(content, str):
            logger.warning(
                "Provider content is not a string (type=%s); treating as empty.",
                type(content).__name__,
            )
            return ""
        return content
    except Exception:
        logger.warning("Could not extract content from LLMResponse; treating as empty.")
        return ""


def _normalise_whitespace(text: str) -> str:
    """Normalise whitespace in *text* safely.

    - Strips leading/trailing whitespace.
    - Collapses sequences of 3+ blank lines into a single blank line.
    - Preserves intentional single blank lines (paragraph breaks).
    - Never raises.
    """
    if not text:
        return ""
    # Collapse runs of 3+ newlines to 2 (one blank line).
    normalised = re.sub(r"\n{3,}", "\n\n", text)
    return normalised.strip()


def _truncate(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars* characters, appending an indicator."""
    if len(text) <= max_chars:
        return text
    logger.warning(
        "Provider summary truncated from %d to %d characters.", len(text), max_chars
    )
    return text[:max_chars] + " [truncated]"


def _determine_confidence(
    included_chunks: list["IncludedChunk"] | None,
    file_path: str | None,
) -> ResponseConfidence:
    """Determine response-level confidence for a free-text LLM answer.

    For free-text responses the confidence level is always UNKNOWN because
    individual model claims have not been mapped to evidence items.  The
    evidence list records what was available to the model so callers can
    inspect it, but availability of inputs does not confirm the accuracy of
    the model's statements.

    Rules
    -----
    - Chunks present  → UNKNOWN, evidence list carries retrieved-chunk refs.
    - No chunks       → UNKNOWN, evidence list carries source-code ref.
    - No fabrication: evidence items reference only what was actually supplied.
    """
    if included_chunks:
        return ResponseConfidence.unknown_with_chunks(
            included_chunks,
            notes=(
                "Free-text response: claims not individually mapped to evidence. "
                "Retrieved chunks listed as available context."
            ),
        )
    # Source code is always submitted — record it as available context.
    return ResponseConfidence.unknown_with_source_code(
        file_path,
        notes=(
            "Free-text response: claims not individually mapped to evidence. "
            "Source code listed as available context."
        ),
    )
