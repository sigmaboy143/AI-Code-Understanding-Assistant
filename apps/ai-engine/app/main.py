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

Observability
-------------
Every request is assigned a correlation ID, echoed in the ``X-Request-ID``
response header, and recorded once in the access log with its status, outcome,
and duration.  Each failure is additionally logged with the same
``error_code`` the client receives, so engine failure, provider failure, and
provider timeout stay distinguishable in the logs alone.  See
``app/observability.py``; none of this alters the contract above.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.observability import install_observability, resolve_log_level
from app.orchestrator import OrchestratorService
from app.providers.base import ProviderError
from app.schemas.code_understanding import (
    CodeUnderstandingRequest,
    CodeUnderstandingResponse,
)
from app.schemas.errors import make_error

logger = logging.getLogger(__name__)

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

# Correlation IDs, the access log, and the log handler for the `app` logger
# tree.  Installed here so importing `app.main` is all that is required.
install_observability(app, level=resolve_log_level(settings.log_level))


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Override FastAPI's default 422 handler to use the stable error envelope.

    The rejected payload is deliberately not logged: it can be large, and it may
    carry whatever the caller submitted.  Only the location and count of the
    validation problems are recorded.
    """
    logger.info(
        "Request validation failed for %s %s.",
        request.method,
        request.url.path,
        extra={
            "error_code": "VALIDATION_ERROR",
            "validation_errors": len(exc.errors()),
        },
    )
    return JSONResponse(
        status_code=422,
        content=make_error("VALIDATION_ERROR", "Request validation failed."),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any exception that escapes the route handler."""
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        extra={"error_code": "INTERNAL_ERROR"},
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
        logger.error(
            "Failed to build provider '%s': %s",
            settings.provider,
            exc,
            extra={"error_code": "PROVIDER_UNAVAILABLE", "provider": settings.provider},
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
        provider_name = exc.provider or settings.provider
        # Distinguish timeout from generic provider errors.
        if any(kw in msg.lower() for kw in _TIMEOUT_KEYWORDS):
            logger.warning(
                "Provider '%s' timed out: %s",
                provider_name,
                msg,
                extra={"error_code": "PROVIDER_TIMEOUT", "provider": provider_name},
            )
            return JSONResponse(
                status_code=504,
                content=make_error(
                    "PROVIDER_TIMEOUT",
                    "The AI provider did not respond in time. Please try again.",
                ),
            )
        logger.error(
            "Provider '%s' failed: %s",
            provider_name,
            msg,
            extra={"error_code": "PROVIDER_ERROR", "provider": provider_name},
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
            "Timed out waiting for provider '%s'.",
            settings.provider,
            extra={"error_code": "PROVIDER_TIMEOUT", "provider": settings.provider},
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
            "Unexpected error during analysis: %s",
            exc,
            extra={"error_code": "INTERNAL_ERROR", "provider": settings.provider},
        )
        return JSONResponse(
            status_code=500,
            content=make_error("INTERNAL_ERROR", "An unexpected error occurred."),
        )
