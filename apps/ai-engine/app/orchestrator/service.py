"""Orchestrator service.

Responsibilities
----------------
1. Accept a ``CodeUnderstandingRequest`` (Task-2 schema).
2. Build an ``LLMRequest`` (system prompt + user message).
3. Delegate to the injected ``LLMProvider`` (Task-3 interface).
4. Parse the ``LLMResponse`` into a ``CodeUnderstandingResponse``.
5. Propagate ``ProviderError`` without wrapping it in additional layers.

Design notes
------------
- The service is provider-agnostic; no concrete provider is imported here.
- Prompt construction is isolated in ``_build_messages`` so it can be extended
  (e.g., with RAG context, evidence, or agent instructions) without touching
  the rest of the service.
- Response parsing is isolated in ``_parse_response`` for the same reason.
- All public methods are async so callers can use the same concurrency model
  regardless of whether the underlying provider is sync or async.
"""

from __future__ import annotations

from app.providers.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from app.schemas.code_understanding import (
    AnalysisMetadata,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
)

_SYSTEM_PROMPT = (
    "You are an expert software engineer. "
    "Analyse the provided source code and answer the user's request. "
    "Be concise, accurate, and language-agnostic. "
    "Do not fabricate facts about the code."
)


class OrchestratorService:
    """Coordinates a code-understanding request with an LLM provider.

    Parameters
    ----------
    provider:
        Any object that implements ``LLMProvider``.  The service never
        references a concrete provider class so it remains testable with a
        simple mock.

    Example::

        service = OrchestratorService(provider=my_provider)
        response = await service.analyse(request)
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyse(self, request: CodeUnderstandingRequest) -> CodeUnderstandingResponse:
        """Analyse *request* using the configured LLM provider.

        Parameters
        ----------
        request:
            A validated ``CodeUnderstandingRequest``.

        Returns
        -------
        CodeUnderstandingResponse
            Typed result with at least a ``summary`` and ``metadata``.

        Raises
        ------
        ProviderError
            Propagated directly from the provider when the LLM call fails.
        """
        llm_request = self._build_llm_request(request)
        llm_response = await self._provider.complete(llm_request)
        return self._parse_response(llm_response, request)

    # ------------------------------------------------------------------
    # Prompt construction (extensible hook for RAG / context builders)
    # ------------------------------------------------------------------

    def _build_llm_request(self, request: CodeUnderstandingRequest) -> LLMRequest:
        """Convert a ``CodeUnderstandingRequest`` into an ``LLMRequest``.

        Future enhancements (RAG retrieval, evidence injection, specialised
        agent instructions) should extend this method rather than touching
        ``analyse``.
        """
        messages = self._build_messages(request)
        return LLMRequest(messages=messages)

    def _build_messages(self, request: CodeUnderstandingRequest) -> list[LLMMessage]:
        """Construct the ordered list of prompt messages."""
        system_msg = LLMMessage(role="system", content=_SYSTEM_PROMPT)
        user_msg = LLMMessage(role="user", content=self._format_user_message(request))
        return [system_msg, user_msg]

    @staticmethod
    def _format_user_message(request: CodeUnderstandingRequest) -> str:
        """Build the user-facing portion of the prompt from request fields."""
        parts: list[str] = []

        # File path context
        if request.file_path:
            parts.append(f"File: {request.file_path}")

        # Language
        parts.append(f"Language: {request.language.value}")

        # Requested analyses
        analysis_labels = ", ".join(a.value for a in request.analyses)
        parts.append(f"Requested analyses: {analysis_labels}")

        # Source code
        parts.append(f"\nSource code:\n```{request.language.value}\n{request.source_code}\n```")

        # Optional question
        if request.question:
            parts.append(f"\nQuestion: {request.question}")

        # Optional extra context (e.g., error output, related code)
        if request.context:
            parts.append(f"\nAdditional context:\n{request.context}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing (extensible hook for evidence extraction, scoring)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(
        llm_response: LLMResponse,
        request: CodeUnderstandingRequest,
    ) -> CodeUnderstandingResponse:
        """Convert an ``LLMResponse`` into a ``CodeUnderstandingResponse``.

        Currently maps the full LLM completion text to the ``summary`` field.
        Future enhancements (structured extraction, evidence scoring, JSON
        mode parsing) should extend this method without altering ``analyse``.
        """
        summary_text = llm_response.content.strip() or "No summary produced by provider."

        metadata = AnalysisMetadata(
            language=request.language,
            file_path=request.file_path,
            analyses=list(request.analyses),
        )

        return CodeUnderstandingResponse(
            summary=summary_text,
            metadata=metadata,
        )
