"""FastAPI application entry point.

Routes
------
GET  /health                   — liveness check (always returns 200 {"status":"ok"})
GET  /ready                    — readiness check (200 if service can accept requests)
POST /api/v1/code-understanding — code analysis endpoint

Error contract
--------------
All non-2xx responses carry a JSON body of the form::

    {
        "error": {
            "code": "<SCREAMING_SNAKE_CASE>",
            "message": "<human-readable, no secrets>"
        }
    }

Status code mapping:
    422  VALIDATION_ERROR     — Pydantic validation failure (FastAPI default)
    503  PROVIDER_UNAVAILABLE — provider not reachable / service not configured
    504  PROVIDER_TIMEOUT     — provider call timed out
    502  PROVIDER_ERROR       — provider returned an unexpected error
    500  INTERNAL_ERROR       — all other unhandled exceptions
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.logging_context import (
    REQUEST_ID_HEADER,
    correlation_suffix,
    new_request_id,
    set_request_id,
)
from app.orchestrator import OrchestratorService
from app.providers.base import ProviderError
from app.schemas.code_understanding import (
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
)
from app.schemas.errors import make_error
from app.adapters.iretrieval_adapter import RepositoryRetrievalAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Without this, the ``app.*`` loggers propagate to a root logger that has no
# handler, so Python's ``lastResort`` handler emits WARNING and above only —
# which would silently discard every INFO line the access log and the provider
# timing depend on.  ``basicConfig`` is a no-op when the root logger already
# has a handler, so an operator's own configuration always wins.
_LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)

#: Probes are logged at DEBUG so a readiness poll every few seconds cannot
#: bury the lines an operator actually needs.
_QUIET_PATHS = frozenset({"/health", "/ready"})

# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------

_TIMEOUT_KEYWORDS = ("timed out", "timeout")


def _build_provider():
    """Construct the configured LLM provider.

    Returns the concrete provider instance for the configured backend.
    Raises ``RuntimeError`` for unknown provider names.
    """
    name = (settings.provider or "").lower()
    if name == "ollama":
        from app.providers.ollama import OllamaProvider

        return OllamaProvider(
            base_url=settings.provider_base_url,
            model=settings.model,
            timeout=settings.request_timeout,
        )
    raise RuntimeError(f"Unknown provider: '{settings.provider}'")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Engine",
    description="AI Engine foundation for code understanding, RAG, and reasoning.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Retrieve request/response schemas
# ---------------------------------------------------------------------------


class RetrieveRequest(BaseModel):
    """Request body for the retrieval endpoint."""
    repository_path: str = Field(description="Absolute path to the repository root.")
    query: str = Field(description="Natural-language question.")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum chunks to return.")


class RetrieveChunkItem(BaseModel):
    """A single evidence chunk in the retrieval response."""
    file_path: str
    symbol: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    relevance_score: float
    chunk_id: str
    content: str


class RetrieveResponse(BaseModel):
    """Response from the retrieval endpoint."""
    chunks: List[RetrieveChunkItem]
    query: str
    repository_path: str
    top_k: int


# ---------------------------------------------------------------------------
# Request correlation and access log
# ---------------------------------------------------------------------------


@app.middleware("http")
async def _access_log(request: Request, call_next):
    """Bind a request identifier and log one line per completed request.

    Every response — success, provider failure, or validation rejection —
    produces exactly one line carrying the request id, method, path, status,
    and wall-clock duration.  That is the minimum needed to answer "which
    request was slow?" and "which log lines belong to this failure?".

    The identifier is taken from an inbound ``X-Request-ID`` when present so an
    upstream service's own correlation id is preserved, and is echoed back on
    the response so a caller can quote it.  This adds a response header only;
    the documented JSON bodies are unchanged.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
    set_request_id(request_id)

    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        suffix = correlation_suffix(
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
            outcome="ok" if status_code < 400 else "error",
        )
        log = logger.debug if request.url.path in _QUIET_PATHS else logger.info
        log("request completed%s", suffix)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Override FastAPI's default 422 handler to use the stable error envelope."""
    # The rejected field values are deliberately not logged: a rejected payload
    # is unvalidated caller input and may contain anything.
    logger.info("request rejected%s", correlation_suffix(outcome="validation_error"))
    return JSONResponse(
        status_code=422,
        content=make_error("VALIDATION_ERROR", "Request validation failed."),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any exception that escapes the route handler."""
    logger.exception(
        "unhandled exception%s",
        correlation_suffix(method=request.method, path=request.url.path, outcome="internal_error"),
    )
    return JSONResponse(
        status_code=500,
        content=make_error("INTERNAL_ERROR", "An unexpected error occurred."),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Liveness check — always returns 200 while the process is running."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    """Readiness check.

    Returns 200 when the service has the minimum configuration required to
    accept code-understanding requests.

    **No real LLM call is made.**  The check verifies only that:
    - A provider name is set.
    - Cloud providers that require an API key have one configured.

    Returns 503 when the service is not ready to accept requests.
    """
    if not settings.is_configured:
        return JSONResponse(
            status_code=503,
            content=make_error(
                "PROVIDER_UNAVAILABLE",
                "The AI provider is not configured. "
                "Set PROVIDER and PROVIDER_API_KEY (if required) in the environment.",
            ),
        )
    return {"status": "ready"}


@app.post(
    "/api/v1/code-understanding",
    response_model=CodeUnderstandingResponse,
    status_code=200,
    responses={
        422: {"description": "Validation error"},
        502: {"description": "Provider error"},
        503: {"description": "Provider unavailable"},
        504: {"description": "Provider timeout"},
        500: {"description": "Internal error"},
    },
)
async def code_understanding(request: CodeUnderstandingRequest) -> CodeUnderstandingResponse:
    """Analyse source code using the configured LLM provider.

    Accepts a ``CodeUnderstandingRequest`` and returns a
    ``CodeUnderstandingResponse``.

    Error codes returned:
    - **422 VALIDATION_ERROR** — request body fails validation.
    - **503 PROVIDER_UNAVAILABLE** — provider cannot be constructed/reached.
    - **504 PROVIDER_TIMEOUT** — provider did not respond within the timeout.
    - **502 PROVIDER_ERROR** — provider returned an error.
    - **500 INTERNAL_ERROR** — unexpected server failure.
    """
    # Build provider — 503 if not reachable/configured
    try:
        provider = _build_provider()
    except Exception as exc:
        # The configured provider name plus the exception type fully identify
        # this failure (the only raise here is an unknown provider name), so the
        # exception *message* is not logged — a broad handler must never be the
        # place arbitrary text starts reaching the log.
        logger.error(
            "failed to build provider%s",
            correlation_suffix(
                provider=settings.provider,
                outcome="provider_unavailable",
                detail=type(exc).__name__,
            ),
        )
        return JSONResponse(
            status_code=503,
            content=make_error(
                "PROVIDER_UNAVAILABLE",
                "The AI provider is unavailable.",
            ),
        )

    service = OrchestratorService(provider=provider)

    try:
        return await service.analyse(request)

    except ProviderError as exc:
        msg = str(exc)
        # Distinguish timeout from generic provider errors.
        if any(kw in msg.lower() for kw in _TIMEOUT_KEYWORDS):
            logger.warning(
                "provider timeout%s",
                correlation_suffix(
                    provider=exc.provider or settings.provider,
                    outcome="provider_timeout",
                ),
            )
            return JSONResponse(
                status_code=504,
                content=make_error(
                    "PROVIDER_TIMEOUT",
                    "The AI provider did not respond in time. Please try again.",
                ),
            )
        # ``msg`` is constructed by the provider from its own status code and
        # base URL.  It never carries the upstream response body or the API key,
        # and it is not sent to the caller, so it is safe to log.
        logger.error(
            "provider error%s",
            correlation_suffix(
                provider=exc.provider or settings.provider,
                outcome="provider_error",
                detail=msg,
            ),
        )
        return JSONResponse(
            status_code=502,
            content=make_error(
                "PROVIDER_ERROR",
                "The AI provider returned an error.",
            ),
        )

    except asyncio.TimeoutError:
        logger.warning(
            "asyncio timeout waiting for provider%s",
            correlation_suffix(
                provider=settings.provider, outcome="provider_timeout"
            ),
        )
        return JSONResponse(
            status_code=504,
            content=make_error(
                "PROVIDER_TIMEOUT",
                "The AI provider did not respond in time. Please try again.",
            ),
        )

    except Exception as exc:
        logger.exception(
            "unexpected error during analysis%s",
            correlation_suffix(
                provider=settings.provider,
                outcome="internal_error",
                detail=type(exc).__name__,
            ),
        )
        return JSONResponse(
            status_code=500,
            content=make_error("INTERNAL_ERROR", "An unexpected error occurred."),
        )


# ---------------------------------------------------------------------------
# Retrieval endpoint
# ---------------------------------------------------------------------------

# Single shared adapter instance — stateless (ingestion is cached in
# app.retrieval.service._repo_index, so re-using the instance is safe).
_retrieval_adapter = RepositoryRetrievalAdapter()


@app.post(
    "/api/v1/retrieve",
    response_model=RetrieveResponse,
    status_code=200,
    responses={
        422: {"description": "Validation error"},
        500: {"description": "Internal error"},
    },
)
def retrieve(request: RetrieveRequest) -> RetrieveResponse:
    """Retrieve the top-k most relevant source chunks for a natural-language query.

    Accepts a ``RetrieveRequest`` with a repository path and a query string.
    Returns ranked chunks with file path, symbol, line range, and actual
    source-code content.

    This endpoint is designed to be called by the NestJS API's
    ``RealRetrievalAdapter`` so it can attach ``evidence.code`` before sending
    the evidence to the Gemma adapter.
    """
    try:
        result = _retrieval_adapter.search(
            request.repository_path,
            request.query,
            top_k=request.top_k,
        )
    except Exception as exc:
        logger.exception(
            "retrieval error%s",
            correlation_suffix(
                outcome="internal_error",
                detail=type(exc).__name__,
            ),
        )
        return JSONResponse(
            status_code=500,
            content=make_error("INTERNAL_ERROR", "Retrieval failed."),
        )

    chunks = [
        RetrieveChunkItem(
            file_path=chunk.file_path,
            symbol=chunk.symbol,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            relevance_score=chunk.relevance_score,
            chunk_id=chunk.chunk_id,
            content=chunk.content,
        )
        for chunk in result.chunks
    ]

    return RetrieveResponse(
        chunks=chunks,
        query=request.query,
        repository_path=request.repository_path,
        top_k=request.top_k,
    )
