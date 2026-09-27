"""Documentation Agent (Task 15A).

Purpose
-------
Answer questions from supplied documentation.  The agent consumes README
files, Markdown documents, docstrings, API documentation, architecture notes,
and configuration documentation that are explicitly supplied by the caller.

The agent never:
- Crawls the internet.
- Reads the file system.
- Invents undocumented behaviour.

Input context
-------------
``DocumentationContext`` may contain:
- readme          — README text
- markdown_files  — {filename: content} mapping of Markdown documents
- docstrings      — {symbol: docstring} mapping
- api_docs        — raw API documentation text
- architecture_notes — architecture documentation text
- config_docs     — configuration documentation text
- question        — the question to answer

Evidence and confidence
-----------------------
- CONFIRMED: answer is directly stated in one of the supplied documents
- INFERRED:  answer is a plausible conclusion from supplied documents
- UNKNOWN:   the supplied documentation does not answer the question

Limitations
-----------
- The agent does not parse or execute code.
- All answers are derived from the supplied text only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    ResponseConfidence,
)


# ---------------------------------------------------------------------------
# Input context models
# ---------------------------------------------------------------------------


class DocumentationContext(BaseModel):
    """Structured documentation context supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    readme: str | None = Field(
        default=None,
        description="README content.",
    )
    markdown_files: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of {filename: content} for Markdown documents.",
    )
    docstrings: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of {symbol_name: docstring} pairs.",
    )
    api_docs: str | None = Field(
        default=None,
        description="API documentation text.",
    )
    architecture_notes: str | None = Field(
        default=None,
        description="Architecture documentation text.",
    )
    config_docs: str | None = Field(
        default=None,
        description="Configuration documentation text.",
    )
    question: str | None = Field(
        default=None,
        description="The question to answer using the supplied documentation.",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class DocumentationSection(BaseModel):
    """A relevant documentation section that contributes to the answer."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Source label, e.g. 'readme', 'api_docs', 'docstring:MyClass'.")
    excerpt: str = Field(description="Relevant excerpt from the documentation.")
    relevance: ConfidenceLevel = ConfidenceLevel.CONFIRMED


class DocumentationResult(BaseModel):
    """Structured output of the Documentation Agent.

    Fields
    ------
    answer:
        The answer derived from the supplied documentation.
        Set to 'UNKNOWN' when the documentation does not answer the question.
    relevant_sections:
        Documentation sections that contributed to the answer.
    documented_facts:
        Facts that are explicitly stated in the supplied documentation.
    inferred_facts:
        Facts inferred from the documentation (not explicitly stated).
    limitations:
        What the agent cannot determine from the supplied documentation.
    confidence:
        Evidence-backed confidence for the answer.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        description="Answer from supplied documentation, or UNKNOWN."
    )
    relevant_sections: list[DocumentationSection] = Field(default_factory=list)
    documented_facts: list[str] = Field(
        default_factory=list,
        description="Facts explicitly stated in the supplied documentation.",
    )
    inferred_facts: list[str] = Field(
        default_factory=list,
        description="Facts inferred from the documentation.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="What the agent cannot determine from the supplied documentation.",
    )
    confidence: ResponseConfidence = Field(
        default_factory=ResponseConfidence.unknown,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class DocumentationAgent:
    """Answers questions from supplied documentation context.

    This agent is stateless.  Every call to ``analyse`` is independent.

    Usage::

        agent = DocumentationAgent()
        result = agent.analyse(context)
    """

    def analyse(self, context: DocumentationContext) -> DocumentationResult:
        """Produce a ``DocumentationResult`` from the supplied context.

        Rules
        -----
        - Only use information present in *context*.
        - Return UNKNOWN when the documentation does not answer the question.
        - Never invent undocumented behaviour.
        - Build evidence items only from fields that are actually populated.

        Parameters
        ----------
        context:
            Structured documentation context supplied by the caller.

        Returns
        -------
        DocumentationResult
            Deterministic result derived exclusively from the supplied context.
        """
        evidence: list[EvidenceItem] = []
        sections: list[DocumentationSection] = []
        documented_facts: list[str] = []
        limitations: list[str] = []

        # ── Collect all documentation into named buckets ─────────────────
        doc_buckets = self._collect_buckets(context)

        if not doc_buckets:
            return DocumentationResult(
                answer="UNKNOWN: No documentation was supplied.",
                limitations=[
                    "No documentation was supplied to the agent. "
                    "Supply readme, markdown_files, docstrings, api_docs, "
                    "architecture_notes, or config_docs."
                ],
                confidence=ResponseConfidence.unknown(
                    notes="No documentation context supplied."
                ),
            )

        # ── Build evidence and sections from available buckets ───────────
        for source_label, content in doc_buckets.items():
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description=f"Supplied documentation: {source_label}",
                )
            )
            sections.append(
                DocumentationSection(
                    source=source_label,
                    excerpt=self._excerpt(content),
                    relevance=ConfidenceLevel.CONFIRMED,
                )
            )
            documented_facts.append(
                f"Documentation available: {source_label}"
            )

        # ── Answer the question if one was supplied ───────────────────────
        answer, answer_confidence = self._answer_question(context, doc_buckets, evidence)

        # ── Identify limitations ─────────────────────────────────────────
        if not context.question:
            limitations.append(
                "No question was supplied; the agent summarised available documentation."
            )

        return DocumentationResult(
            answer=answer,
            relevant_sections=sections,
            documented_facts=documented_facts,
            limitations=limitations,
            confidence=answer_confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_buckets(context: DocumentationContext) -> dict[str, str]:
        """Collect all non-empty documentation content into labelled buckets."""
        buckets: dict[str, str] = {}

        if context.readme:
            buckets["readme"] = context.readme
        if context.api_docs:
            buckets["api_docs"] = context.api_docs
        if context.architecture_notes:
            buckets["architecture_notes"] = context.architecture_notes
        if context.config_docs:
            buckets["config_docs"] = context.config_docs
        for filename, content in context.markdown_files.items():
            if content.strip():
                buckets[f"markdown:{filename}"] = content
        for symbol, docstring in context.docstrings.items():
            if docstring.strip():
                buckets[f"docstring:{symbol}"] = docstring

        return buckets

    @staticmethod
    def _excerpt(content: str, max_chars: int = 300) -> str:
        """Return a short excerpt from a documentation block."""
        stripped = content.strip()
        if len(stripped) <= max_chars:
            return stripped
        return stripped[:max_chars] + "..."

    def _answer_question(
        self,
        context: DocumentationContext,
        doc_buckets: dict[str, str],
        evidence: list[EvidenceItem],
    ) -> tuple[str, ResponseConfidence]:
        """Find the best answer to the supplied question from the documentation.

        Strategy
        --------
        1. If no question: summarise available documentation sources.
        2. Search each bucket for content that mentions keywords from the question.
        3. If a matching bucket is found: return CONFIRMED with that excerpt.
        4. If no matching bucket: return UNKNOWN.
        """
        if not context.question:
            source_list = ", ".join(doc_buckets.keys())
            answer = f"Available documentation sources: {source_list}."
            return answer, ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes="Documentation sources listed; no specific question was asked.",
            )

        question_lower = context.question.lower()
        keywords = [w for w in question_lower.split() if len(w) > 3]

        best_source: str | None = None
        best_excerpt: str | None = None

        for source_label, content in doc_buckets.items():
            content_lower = content.lower()
            if any(kw in content_lower for kw in keywords):
                best_source = source_label
                best_excerpt = self._excerpt(content)
                break

        if best_source and best_excerpt:
            answer_evidence = [
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description=f"Answer found in: {best_source}",
                )
            ]
            return (
                f"From {best_source}: {best_excerpt}",
                ResponseConfidence(
                    level=ConfidenceLevel.CONFIRMED,
                    evidence=answer_evidence,
                    notes=f"Answer sourced from supplied documentation: {best_source}.",
                ),
            )

        return (
            f"UNKNOWN: The supplied documentation does not answer: '{context.question}'",
            ResponseConfidence.unknown(
                notes=(
                    "The question could not be answered from the supplied documentation. "
                    f"Available sources: {', '.join(doc_buckets.keys())}."
                )
            ),
        )
