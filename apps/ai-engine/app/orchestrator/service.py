"""Orchestrator service.

Responsibilities
----------------
1. Accept a ``CodeUnderstandingRequest`` (Task-2 schema).
2. Build an ``LLMRequest`` via the reasoning layer (Task-6).
3. Delegate to the injected ``LLMProvider`` (Task-3 interface).
4. Parse the ``LLMResponse`` into a ``CodeUnderstandingResponse``.
5. Propagate ``ProviderError`` without wrapping it in additional layers.

Design notes
------------
- The service is provider-agnostic; no concrete provider is imported here.
- Prompt construction is fully delegated to ``app.reasoning`` so reasoning
  logic can evolve without touching the orchestration loop.
- Response parsing is isolated in ``_parse_response`` for the same reason.
- ``analyse`` accepts an optional ``retrieved_chunks`` argument so the
  retrieval layer (Task 7) can inject RAG context without an API change.
- All public methods are async so callers can use the same concurrency model
  regardless of whether the underlying provider is sync or async.
"""

from __future__ import annotations

from typing import Sequence

from app.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.reasoning import build_reasoning_request
from app.schemas.code_understanding import (
    AnalysisMetadata,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
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

    async def analyse(
        self,
        request: CodeUnderstandingRequest,
        retrieved_chunks: Sequence | None = None,
    ) -> CodeUnderstandingResponse:
        """Analyse *request* using the configured LLM provider.

        Parameters
        ----------
        request:
            A validated ``CodeUnderstandingRequest``.
        retrieved_chunks:
            Optional RAG context from the retrieval layer (Task 7).
            When provided the chunks are injected into the prompt.

        Returns
        -------
        CodeUnderstandingResponse
            Typed result with at least a ``summary`` and ``metadata``.

        Raises
        ------
        ProviderError
            Propagated directly from the provider when the LLM call fails.
        """
        llm_request = self._build_llm_request(request, retrieved_chunks)
        llm_response = await self._provider.complete(llm_request)
        return self._parse_response(llm_response, request)

    # ------------------------------------------------------------------
    # Prompt construction — delegates to the reasoning layer
    # ------------------------------------------------------------------

    def _build_llm_request(
        self,
        request: CodeUnderstandingRequest,
        retrieved_chunks: Sequence | None = None,
    ) -> LLMRequest:
        """Convert a ``CodeUnderstandingRequest`` into an ``LLMRequest``.

        Delegates to ``app.reasoning.build_reasoning_request`` so that all
        prompt logic lives in one place and can be enriched (RAG context,
        evidence, agent instructions) without touching ``analyse``.
        """
        return build_reasoning_request(request, retrieved_chunks)

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
