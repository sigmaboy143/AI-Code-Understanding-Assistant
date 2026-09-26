"""Code-understanding reasoning layer.

This module is the single place where the mapping from a
``CodeUnderstandingRequest`` to an ``LLMRequest`` is defined.

Design principles
-----------------
- **Grounded** — prompts explicitly instruct the model not to fabricate
  repository facts (Git history, commits, tests, external dependencies)
  that are not present in the supplied input.
- **Analysis-aware** — every requested ``AnalysisType`` generates a
  concrete instruction in the prompt so the model knows what to focus on.
- **Question-first** — when the request includes a question the prompt
  prioritises answering it.
- **Context-aware** — supplementary context (error output, related code)
  is injected into the prompt when provided.
- **Extensible** — ``build_reasoning_request`` accepts an optional list of
  ``RetrievedChunk`` objects (Task 7) so RAG context can be injected later
  without changing the function signature used here.

Limitations
-----------
- The reasoning is single-turn; there is no multi-agent orchestration.
- There is no structured JSON extraction; the model's free-text completion
  is placed into ``CodeUnderstandingResponse.summary``.
- Confidence scoring is not implemented.
- Git history, commits, and PRs are never inferred; they must be supplied
  in ``context`` by the caller if needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from app.providers.base import LLMMessage, LLMRequest
from app.schemas.code_understanding import AnalysisType, CodeUnderstandingRequest

if TYPE_CHECKING:
    # Imported lazily to avoid a circular dependency at runtime;
    # the retrieval module is Task 7 and may not exist yet.
    from app.retrieval.base import RetrievedChunk


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert software engineer performing code analysis.

RULES — follow these strictly:
1. Base ALL answers on the source code and context provided in this message.
2. Do NOT invent Git history, commits, pull requests, tests, external \
dependencies, file structures, or other repository facts that are not \
explicitly supplied.
3. If information required to answer is missing, say so clearly and explain \
what additional context would be needed.
4. Be concise and precise.
5. Use the exact language identifier supplied when referencing the language.
"""


# ---------------------------------------------------------------------------
# Analysis-type instruction map
# ---------------------------------------------------------------------------

_ANALYSIS_INSTRUCTIONS: dict[AnalysisType, str] = {
    AnalysisType.EXPLANATION: (
        "Provide a clear explanation of what the code does: "
        "start with a high-level overview, then walk through the key logic."
    ),
    AnalysisType.ERROR_EXPLANATION: (
        "Identify and explain any errors, exceptions, or bugs visible in the "
        "code or described in the context. "
        "List likely causes and concrete suggested fixes."
    ),
    AnalysisType.STRUCTURE: (
        "Describe the structural elements of the code: "
        "list all top-level functions, classes, and methods with a brief "
        "summary of each. Note line numbers when they are visible."
    ),
    AnalysisType.DEPENDENCIES: (
        "List every import, library, or module the code depends on. "
        "Classify each as builtin, standard-library, internal, or external. "
        "Only include dependencies that appear in the supplied code — "
        "do not infer transitive dependencies."
    ),
    AnalysisType.IMPROVEMENTS: (
        "Suggest concrete, actionable improvements to the code. "
        "For each suggestion state: what to change, why, and the severity "
        "(info / low / medium / high)."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_reasoning_request(
    request: CodeUnderstandingRequest,
    retrieved_chunks: Sequence["RetrievedChunk"] | None = None,
) -> LLMRequest:
    """Build an ``LLMRequest`` for a code-understanding analysis.

    Parameters
    ----------
    request:
        The validated request from the HTTP layer.
    retrieved_chunks:
        Optional RAG context chunks from the retrieval layer (Task 7).
        When provided their content is injected into the prompt under a
        ``Retrieved context`` heading.

    Returns
    -------
    LLMRequest
        A provider-agnostic prompt ready to be sent to any ``LLMProvider``.
    """
    system_msg = LLMMessage(role="system", content=_SYSTEM_PROMPT)
    user_msg = LLMMessage(
        role="user",
        content=_format_user_message(request, retrieved_chunks),
    )
    return LLMRequest(messages=[system_msg, user_msg])


def _format_user_message(
    request: CodeUnderstandingRequest,
    retrieved_chunks: Sequence["RetrievedChunk"] | None,
) -> str:
    """Assemble the user-turn message from all available inputs."""
    parts: list[str] = []

    # ── Identity / location ──────────────────────────────────────────────
    if request.file_path:
        parts.append(f"File: {request.file_path}")
    parts.append(f"Language: {request.language.value}")

    # ── Requested analyses ───────────────────────────────────────────────
    instructions = _build_analysis_instructions(request.analyses)
    parts.append(f"Requested analyses:\n{instructions}")

    # ── Source code ──────────────────────────────────────────────────────
    parts.append(
        f"\nSource code:\n```{request.language.value}\n{request.source_code}\n```"
    )

    # ── Explicit question (takes priority over general analyses) ─────────
    if request.question:
        parts.append(
            f"\nQuestion (answer this first, then provide the requested analyses):\n"
            f"{request.question}"
        )

    # ── Supplementary context (error output, related code, etc.) ────────
    if request.context:
        parts.append(
            f"\nAdditional context supplied by the caller "
            f"(treat as ground truth, do not contradict it):\n{request.context}"
        )

    # ── RAG / retrieved chunks (Task 7 extension point) ─────────────────
    if retrieved_chunks:
        chunk_lines: list[str] = []
        for chunk in retrieved_chunks:
            header = f"[{chunk.source_type}] {chunk.file_path}"
            if chunk.symbol:
                header += f" — {chunk.symbol}"
            if chunk.line_start is not None:
                header += f" (lines {chunk.line_start}–{chunk.line_end})"
            chunk_lines.append(f"{header}\n{chunk.content}")
        parts.append(
            "\nRetrieved context (use only to supplement your analysis, "
            "do not fabricate details not present here):\n"
            + "\n\n".join(chunk_lines)
        )

    # ── Missing-information reminder ─────────────────────────────────────
    parts.append(
        "\nIf you cannot answer any part of the request from the information "
        "supplied above, explicitly state what is missing."
    )

    return "\n".join(parts)


def _build_analysis_instructions(analyses: list[AnalysisType]) -> str:
    """Return a numbered list of per-analysis instructions."""
    lines: list[str] = []
    for i, analysis in enumerate(analyses, 1):
        instruction = _ANALYSIS_INSTRUCTIONS.get(analysis, f"Perform {analysis.value} analysis.")
        lines.append(f"{i}. [{analysis.value.upper()}] {instruction}")
    return "\n".join(lines)
