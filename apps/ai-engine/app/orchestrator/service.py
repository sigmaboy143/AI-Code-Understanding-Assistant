"""Orchestrator service.

Responsibilities
----------------
1. Accept a ``CodeUnderstandingRequest`` (Task-2 schema).
2. Use the context builder (Task-8) to assemble relevant context.
3. Build an ``LLMRequest`` via the reasoning layer (Task-6).
4. Delegate to the injected ``LLMProvider`` (Task-3 interface).
5. Validate and normalise the raw ``LLMResponse`` (Task-10).
6. Attach evidence-backed confidence to the response (Task-9).
7. Parse the result into a ``CodeUnderstandingResponse``.
8. Propagate ``ProviderError`` without wrapping it in additional layers.

Design notes
------------
- The service is provider-agnostic; no concrete provider is imported here.
- Prompt construction is fully delegated to ``app.reasoning`` so reasoning
  logic can evolve without touching the orchestration loop.
- Context assembly is fully delegated to ``ContextBuilder`` so limits,
  deduplication, and future evidence injection are centralised.
- Response validation / normalisation is delegated to ``validate_llm_response``
  so the orchestrator loop stays clean.
- ``analyse`` accepts an optional ``retrieved_chunks`` argument so the
  retrieval layer (Task 7) can inject RAG context without an API change.
- All public methods are async so callers can use the same concurrency model
  regardless of whether the underlying provider is sync or async.
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

from app.context_builder import ContextBuilder
from app.logging_context import correlation_suffix
from app.output_validation import validate_llm_response
from app.output_validation.dependencies import build_dependency_analysis
from app.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.reasoning import build_reasoning_request
from app.schemas.code_understanding import (
    AnalysisMetadata,
    AnalysisType,
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
    DependencyAnalysis,
    ProgrammingLanguage,
)

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Coordinates a code-understanding request with an LLM provider.

    Parameters
    ----------
    provider:
        Any object that implements ``LLMProvider``.  The service never
        references a concrete provider class so it remains testable with a
        simple mock.
    context_builder:
        Optional ``ContextBuilder`` instance.  Defaults to a new instance
        with the default ``max_chars`` limit.

    Example::

        service = OrchestratorService(provider=my_provider)
        response = await service.analyse(request)
    """

    def __init__(
        self,
        provider: LLMProvider,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._provider = provider
        self._context_builder = context_builder or ContextBuilder()

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
            When provided the chunks are passed through the context builder
            before being injected into the prompt.

        Returns
        -------
        CodeUnderstandingResponse
            Typed result with at least a ``summary``, ``metadata``, and
            ``confidence``.

        Raises
        ------
        ProviderError
            Propagated directly from the provider when the LLM call fails.
        """
        # ── Task 8: assemble context ─────────────────────────────────────
        built_context = self._context_builder.build(request, retrieved_chunks)

        # ── Task 6: build the LLM prompt from the built context ──────────
        llm_request = self._build_llm_request(request, built_context.included_chunks or None)

        # ── Provider call (ProviderError propagates upward) ──────────────
        # Timed separately from the overall request so a slow response can be
        # attributed to the provider rather than to context assembly or
        # validation.  Only the provider's name and the elapsed milliseconds
        # are logged — never the prompt, the source code, or the completion.
        provider_started = time.perf_counter()
        try:
            llm_response = await self._provider.complete(llm_request)
        except Exception:
            logger.warning(
                "provider call failed%s",
                correlation_suffix(
                    provider=type(self._provider).__name__,
                    provider_call_ms=round(
                        (time.perf_counter() - provider_started) * 1000, 2
                    ),
                    outcome="provider_error",
                ),
            )
            raise
        logger.info(
            "provider call completed%s",
            correlation_suffix(
                provider=type(self._provider).__name__,
                model=llm_response.model or "unknown",
                provider_call_ms=round(
                    (time.perf_counter() - provider_started) * 1000, 2
                ),
                outcome="ok",
            ),
        )

        # ── Task 10: validate + normalise the response ───────────────────
        return self._parse_response(llm_response, request, built_context.included_chunks)

    # ------------------------------------------------------------------
    # Prompt construction — delegates to the reasoning layer
    # ------------------------------------------------------------------

    def _build_llm_request(
        self,
        request: CodeUnderstandingRequest,
        included_chunks: list | None = None,
    ) -> LLMRequest:
        """Convert a ``CodeUnderstandingRequest`` into an ``LLMRequest``.

        Delegates to ``app.reasoning.build_reasoning_request`` so that all
        prompt logic lives in one place and can be enriched without touching
        ``analyse``.

        ``included_chunks`` are passed as ``retrieved_chunks`` to the
        reasoning layer so they appear in the prompt.
        """
        return build_reasoning_request(request, included_chunks or None)

    # ------------------------------------------------------------------
    # Response parsing — validates, normalises, attaches evidence
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(
        llm_response: LLMResponse,
        request: CodeUnderstandingRequest,
        included_chunks: list,
    ) -> CodeUnderstandingResponse:
        """Validate and convert an ``LLMResponse`` into a ``CodeUnderstandingResponse``.

        Uses the output validation pipeline (Task 10) to:
        - Detect empty / malformed responses.
        - Normalise whitespace safely.
        - Derive evidence-backed confidence (Task 9).
        - Never silently fabricate data.

        Dependency results are populated only when requested and directly
        established by deterministic source or retrieved-code evidence.
        Other optional structured fields remain null.
        """
        # Task 10: validate + normalise
        summary_text, confidence = validate_llm_response(
            llm_response,
            included_chunks=included_chunks or None,
            file_path=request.file_path,
        )

        metadata = AnalysisMetadata(
            language=request.language,
            file_path=request.file_path,
            analyses=list(request.analyses),
        )

        dependencies = None
        if AnalysisType.DEPENDENCIES in request.analyses:
            if request.language is ProgrammingLanguage.PYTHON:
                evidence_texts = [
                    text
                    for text in [request.context, *(chunk.content for chunk in included_chunks)]
                    if text
                ]
                dependencies = build_dependency_analysis(
                    request.source_code,
                    evidence_texts,
                )
            else:
                dependencies = DependencyAnalysis()

        return CodeUnderstandingResponse(
            summary=summary_text,
            metadata=metadata,
            confidence=confidence,
            dependencies=dependencies,
        )
