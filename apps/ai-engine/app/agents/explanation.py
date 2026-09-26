"""Code Explanation Agent (Task 11).

Purpose
-------
Explain supplied source code using only the code, context, and evidence
that is explicitly provided.  The agent answers a user's question about code,
describes visible control/data flow, and summarises what the code does.

The agent:
- Explains what the code does from the supplied source.
- Explains visible control/data flow present in the code.
- Answers the user's question when one is supplied.
- Uses supplied retrieved chunks and built context.
- Returns UNKNOWN for aspects with insufficient evidence.

The agent never:
- Scans the repository or file system.
- Invents symbols, dependencies, tests, or Git history.
- Builds an AST parser.
- Calls a real LLM (uses the injected LLMProvider for text completion).

Input context
-------------
``ExplanationContext`` contains:
- source_code       — the code to explain (required)
- language          — programming language label
- file_path         — optional repository-relative path
- question          — optional free-form question to answer
- analyses          — optional list of AnalysisType hints
- retrieved_chunks  — optional list of IncludedChunk objects
- user_context      — optional supplementary context text

Evidence and confidence
-----------------------
- CONFIRMED: claim directly supported by submitted source code
- INFERRED:  claim is a plausible conclusion from supplied evidence
- UNKNOWN:   required information is absent

Limitations
-----------
- The agent does not parse or execute code.
- Control/data flow is described textually from the visible code only.
- No AST analysis is performed.
- Claims are not individually mapped to evidence items.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.context_builder.builder import IncludedChunk
from app.evidence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    ResponseConfidence,
)
from app.providers.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from app.schemas.code_understanding import AnalysisType, ProgrammingLanguage


# ---------------------------------------------------------------------------
# Input context models
# ---------------------------------------------------------------------------


class ExplanationContext(BaseModel):
    """Structured context for a code explanation request.

    All fields except ``source_code`` are optional.  When fields are absent
    the agent returns UNKNOWN for the aspects that require them.
    """

    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(
        description="The source code to explain (required)."
    )
    language: ProgrammingLanguage = Field(
        default=ProgrammingLanguage.OTHER,
        description="Programming language of the source code.",
    )
    file_path: str | None = Field(
        default=None,
        description="Repository-relative file path, if known.",
    )
    question: str | None = Field(
        default=None,
        description="Optional free-form question to answer about the code.",
    )
    analyses: list[AnalysisType] = Field(
        default_factory=list,
        description="Optional analysis-type hints.",
    )
    retrieved_chunks: list[IncludedChunk] = Field(
        default_factory=list,
        description="Retrieved context chunks pre-selected by the context builder.",
    )
    user_context: str | None = Field(
        default=None,
        description="Optional supplementary context supplied by the caller.",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class FlowStep(BaseModel):
    """A single step in the described control or data flow."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(description="Step number (1-based).")
    description: str = Field(description="What happens at this step.")
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.CONFIRMED,
        description="Confidence level for this step.",
    )


class ExplanationResult(BaseModel):
    """Structured output of the Code Explanation Agent.

    Fields
    ------
    overview:
        High-level description of what the code does.
        UNKNOWN when no source code is supplied.
    details:
        Longer walkthrough of the code logic.
        None when source code is absent or minimal.
    flow_steps:
        Visible control/data flow described as ordered steps.
        Empty when flow cannot be determined from the supplied code.
    question_answer:
        Answer to the user's question, when one was supplied.
        UNKNOWN when no question or insufficient evidence.
    limitations:
        Aspects the agent cannot determine from the supplied context.
    confidence:
        Evidence-backed confidence for the result.
    """

    model_config = ConfigDict(extra="forbid")

    overview: str = Field(
        description="High-level explanation of what the code does, or UNKNOWN."
    )
    details: str | None = Field(
        default=None,
        description="Longer code walkthrough, or None when not determinable.",
    )
    flow_steps: list[FlowStep] = Field(
        default_factory=list,
        description="Visible control/data flow steps.",
    )
    question_answer: str | None = Field(
        default=None,
        description="Answer to the supplied question, or UNKNOWN when unanswerable.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="What the agent cannot determine from the supplied context.",
    )
    confidence: ResponseConfidence = Field(
        default_factory=ResponseConfidence.unknown,
        description="Evidence-backed confidence for this result.",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert software engineer performing focused code explanation.

RULES — follow these strictly:
1. Base ALL answers ONLY on the source code and context supplied in this message.
2. Do NOT invent Git history, commits, pull requests, tests, external \
dependencies, file structures, or other repository facts that are not \
explicitly supplied.
3. If information required to answer is missing, say "UNKNOWN" and explain \
what additional context would be needed.
4. Describe control flow and data flow only from the visible code.
5. Be concise and precise.
6. When answering a question, answer it first before providing general analysis.
"""


class ExplanationAgent:
    """Explains submitted source code using the injected LLM provider.

    The agent is stateless.  Every call to ``explain`` is independent.
    No LLM is called when ``provider`` is None — a purely deterministic
    result is produced from the supplied context alone.

    Usage::

        provider = MockProvider(response_text="This function sorts a list.")
        agent = ExplanationAgent(provider=provider)
        result = agent.explain(context)

    When no provider is supplied the agent uses a deterministic fallback
    based on what is present in the context — useful for testing confidence
    and evidence behaviour without a real LLM.

    Parameters
    ----------
    provider:
        Any ``LLMProvider`` implementation.  Pass ``None`` to use the
        deterministic no-LLM mode (returns a structured result without
        calling any model).
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    async def explain(self, context: ExplanationContext) -> ExplanationResult:
        """Produce an ``ExplanationResult`` from the supplied context.

        Parameters
        ----------
        context:
            Structured explanation context supplied by the caller.

        Returns
        -------
        ExplanationResult
            Deterministic result derived from the supplied context and,
            when a provider is configured, augmented by an LLM completion.
        """
        if not context.source_code.strip():
            return ExplanationResult(
                overview="UNKNOWN: No source code was supplied.",
                limitations=["No source code supplied; cannot produce an explanation."],
                confidence=ResponseConfidence.unknown(
                    notes="No source code supplied."
                ),
            )

        evidence: list[EvidenceItem] = []
        limitations: list[str] = []

        # Build source-code evidence
        evidence.append(
            EvidenceItem(
                source_type=EvidenceSourceType.SOURCE_CODE,
                file_path=context.file_path,
                description="Submitted source code.",
            )
        )

        # Add evidence from retrieved chunks
        for chunk in context.retrieved_chunks:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.RETRIEVED_CHUNK,
                    file_path=chunk.file_path,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    chunk_id=chunk.chunk_id,
                    description=chunk.symbol or chunk.source_type,
                )
            )

        # Produce the LLM-backed explanation when a provider is injected
        if self._provider is not None:
            llm_request = self._build_llm_request(context)
            llm_response: LLMResponse = await self._provider.complete(llm_request)
            llm_text = (llm_response.content or "").strip() or None
        else:
            llm_text = None
            limitations.append(
                "No LLM provider was supplied; explanation is based on structural "
                "analysis of the code only."
            )

        # Build overview from LLM text or deterministic fallback
        overview = self._derive_overview(context, llm_text)
        details = llm_text if llm_text and len(llm_text) > len(overview) + 10 else None

        # Flow steps from the code structure (deterministic, no LLM needed)
        flow_steps = self._extract_flow_steps(context)

        # Answer the question
        question_answer = self._answer_question(context, llm_text)
        if context.question and question_answer is None:
            limitations.append(
                f"Insufficient evidence to answer: '{context.question}'"
            )

        # Limitations for absent context
        if not context.retrieved_chunks:
            limitations.append(
                "No retrieved context chunks were supplied; explanation is based "
                "on the submitted source code only."
            )

        confidence = self._build_confidence(evidence, context)

        return ExplanationResult(
            overview=overview,
            details=details,
            flow_steps=flow_steps,
            question_answer=question_answer,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_llm_request(context: ExplanationContext) -> LLMRequest:
        """Construct an LLMRequest from the explanation context."""
        parts: list[str] = []

        if context.file_path:
            parts.append(f"File: {context.file_path}")
        parts.append(f"Language: {context.language.value}")

        if context.question:
            parts.append(
                f"\nQuestion (answer this first):\n{context.question}"
            )

        parts.append(
            f"\nSource code:\n```{context.language.value}\n"
            f"{context.source_code}\n```"
        )

        if context.user_context:
            parts.append(
                f"\nAdditional context (treat as ground truth):\n{context.user_context}"
            )

        if context.retrieved_chunks:
            chunk_lines: list[str] = []
            for chunk in context.retrieved_chunks:
                header = f"[{chunk.source_type}] {chunk.file_path}"
                if chunk.symbol:
                    header += f" — {chunk.symbol}"
                if chunk.line_start is not None:
                    header += f" (lines {chunk.line_start}–{chunk.line_end})"
                chunk_lines.append(f"{header}\n{chunk.content}")
            parts.append(
                "\nRetrieved context (use only to supplement your analysis; "
                "do not fabricate details not present here):\n"
                + "\n\n".join(chunk_lines)
            )

        parts.append(
            "\nProvide:\n"
            "1. A high-level overview of what the code does.\n"
            "2. A description of the visible control/data flow.\n"
            "3. Answer the question above if one was supplied.\n"
            "If any information is missing, state UNKNOWN."
        )

        user_msg = LLMMessage(role="user", content="\n".join(parts))
        system_msg = LLMMessage(role="system", content=_SYSTEM_PROMPT)
        return LLMRequest(messages=[system_msg, user_msg])

    @staticmethod
    def _derive_overview(context: ExplanationContext, llm_text: str | None) -> str:
        """Derive the overview from LLM text or fall back to a deterministic summary."""
        if llm_text:
            # Use first non-empty line as a concise overview
            first_line = next(
                (line.strip() for line in llm_text.splitlines() if line.strip()),
                llm_text[:200].strip(),
            )
            return first_line

        # Deterministic fallback: describe the code by what we can see
        lang = context.language.value
        loc = len([l for l in context.source_code.splitlines() if l.strip()])
        hint = f"Source code in {lang} ({loc} non-blank line(s))."
        if context.file_path:
            hint += f" File: {context.file_path}."
        return hint

    @staticmethod
    def _extract_flow_steps(context: ExplanationContext) -> list[FlowStep]:
        """Extract visible flow steps from the source code structure.

        Uses simple line-level heuristics (no AST); only describes
        constructs that are visibly present in the code.
        """
        steps: list[FlowStep] = []
        lines = context.source_code.splitlines()
        step_num = 0

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("def ") or stripped.startswith("async def "):
                step_num += 1
                name = stripped.split("(")[0].replace("def ", "").replace("async ", "").strip()
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Function defined: {name}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
            elif stripped.startswith("class "):
                step_num += 1
                name = stripped.split("(")[0].split(":")[0].replace("class ", "").strip()
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Class defined: {name}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
            elif stripped.startswith("return "):
                step_num += 1
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Returns: {stripped[7:50]}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
            elif stripped.startswith("raise "):
                step_num += 1
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Raises exception: {stripped[6:60]}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
            elif stripped.startswith("if ") or stripped.startswith("elif "):
                step_num += 1
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Conditional branch: {stripped[:80]}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
            elif stripped.startswith("for ") or stripped.startswith("while "):
                step_num += 1
                steps.append(
                    FlowStep(
                        step=step_num,
                        description=f"Loop: {stripped[:80]}",
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )

            # Cap at 20 steps to keep the output focused
            if step_num >= 20:
                break

        return steps

    @staticmethod
    def _answer_question(
        context: ExplanationContext,
        llm_text: str | None,
    ) -> str | None:
        """Return the LLM-provided answer or UNKNOWN."""
        if context.question is None:
            return None
        if llm_text:
            return llm_text
        return f"UNKNOWN: Insufficient evidence to answer '{context.question}'"

    @staticmethod
    def _build_confidence(
        evidence: list[EvidenceItem],
        context: ExplanationContext,
    ) -> ResponseConfidence:
        """Build confidence from available evidence."""
        if not evidence:
            return ResponseConfidence.unknown(notes="No evidence available.")

        # Source code is always present if we reach here
        has_chunks = bool(context.retrieved_chunks)
        if has_chunks:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes=(
                    "Explanation based on submitted source code and retrieved context chunks."
                ),
            )

        return ResponseConfidence(
            level=ConfidenceLevel.CONFIRMED,
            evidence=evidence,
            notes="Explanation based on submitted source code.",
        )
