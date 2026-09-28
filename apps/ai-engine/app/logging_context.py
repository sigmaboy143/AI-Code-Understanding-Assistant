"""Per-request logging context (Phase 33/34).

Purpose
-------
Give every log line produced while serving one inbound request a shared
correlation identifier, so an operator holding a failed response can find the
exact log lines for it.

Why the fields are in the message, not in ``extra``
----------------------------------------------------
``logging``'s ``extra`` dict is invisible unless a formatter is configured to
print it, and the AI Engine deliberately ships no logging configuration.  A
suffix of ``key=value`` pairs in the message itself is therefore used instead:
it is visible under any formatter — including the bare ``uvicorn`` default —
and it stays greppable.

What must never be passed here
------------------------------
:func:`correlation_suffix` accepts arbitrary values, so callers are responsible
for passing only **safe, low-cardinality, non-secret** data: identifiers,
status codes, durations, booleans, and model names.  Never pass API keys,
tokens, request bodies, source code, or LLM output.  The AI Engine's own call
sites follow that rule — see ``app/output_validation/validator.py``, which logs
only counts, type names, and model metadata.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

#: Emitted on every log line so several services' logs can be told apart.
SERVICE_NAME = "ai-engine"

#: Inbound/outbound correlation header.  Reusing the conventional header name
#: means an upstream caller that already stamps requests keeps one identifier
#: across the whole system instead of growing a second, private one.
REQUEST_ID_HEADER = "X-Request-ID"

#: Placeholder used before a request context exists (startup, background work).
NO_REQUEST_ID = "-"

_request_id: ContextVar[str] = ContextVar("ai_request_id", default=NO_REQUEST_ID)


def new_request_id() -> str:
    """Return a fresh request identifier.

    A random UUID4 hex string: unique per request, carries no information
    about the caller, and cannot be guessed from a timestamp.
    """
    return uuid.uuid4().hex


def set_request_id(value: str) -> str:
    """Bind *value* as the current request identifier and return it."""
    _request_id.set(value or NO_REQUEST_ID)
    return _request_id.get()


def get_request_id() -> str:
    """Return the current request identifier, or ``"-"`` outside a request."""
    return _request_id.get()


def correlation_suffix(**fields: object) -> str:
    """Return a ``" key=value"`` suffix for a log message.

    ``service`` and ``request_id`` are always included so that a line can be
    attributed without knowing which module emitted it.  ``None`` values are
    dropped so optional fields do not clutter the line.  An explicit
    ``request_id=`` overrides the ambient one.

    Examples
    --------
    >>> correlation_suffix(outcome="ok", duration_ms=12)  # doctest: +SKIP
    ' service=ai-engine request_id=- outcome=ok duration_ms=12'
    """
    request_id = fields.pop("request_id", None) or get_request_id()
    parts = [f"service={SERVICE_NAME}", f"request_id={request_id}"]
    parts.extend(f"{key}={value}" for key, value in fields.items() if value is not None)
    return " " + " ".join(parts)
