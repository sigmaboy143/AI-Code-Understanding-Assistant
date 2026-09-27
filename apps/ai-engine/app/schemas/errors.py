"""Stable JSON error schema returned by the API on all failure paths.

Every error response body is::

    {
        "error": {
            "code": "<SCREAMING_SNAKE_CASE>",
            "message": "<human-readable, no secrets>"
        }
    }

Status code → error code mapping
---------------------------------
422  VALIDATION_ERROR          — Pydantic / request validation failure
503  PROVIDER_UNAVAILABLE      — provider cannot be reached / not configured
504  PROVIDER_TIMEOUT          — provider call exceeded the configured timeout
502  PROVIDER_ERROR            — provider returned an error or a bad response
500  INTERNAL_ERROR            — unexpected server-side failure
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Inner error object."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Top-level error envelope returned on all non-2xx responses."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def make_error(code: str, message: str) -> dict:
    """Return a plain dict matching the ``ErrorResponse`` shape."""
    return {"error": {"code": code, "message": message}}
