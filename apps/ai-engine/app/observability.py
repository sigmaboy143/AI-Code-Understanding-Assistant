"""Request-scoped correlation, timing, and access logging for the AI Engine.

Scope
-----
This module adds *observability only*.  It does not change the public HTTP
contract: status codes, response bodies, and the error envelope are untouched.
The single addition visible to a caller is the ``X-Request-ID`` response
header, which echoes the correlation ID used in the service's own logs.

What it provides
----------------
1. **Correlation** — every inbound HTTP request gets a request ID.  A
   caller-supplied ``X-Request-ID`` is honoured so an upstream service (such
   as Member 1's NestJS adapter) can join its own logs to these; otherwise a
   fresh UUID is generated.  The ID is stored in a :class:`~contextvars.ContextVar`
   and stamped onto **every** :class:`logging.LogRecord` by a record factory, so
   any log line emitted while handling the request — including one from a
   module that has never heard of this module — carries the same ID.
2. **Access log** — exactly one line per HTTP request with the service name,
   method, path, status code, outcome class, and wall-clock duration.
3. **Logging setup** — the ``app`` logger tree gets a stream handler and a
   level, because nothing else configures it.  Without this the engine's own
   records are discarded: ``uvicorn`` configures its own loggers, not the root
   logger, and the root logger defaults to ``WARNING``.

Safety
------
No credential, prompt, source code, retrieved chunk, or model completion is
ever written to a log record.  Records carry identifiers, counts, sizes,
status codes, and durations only.  A caller-supplied request ID is accepted
only when it matches a conservative character allowlist, so a hostile or
oversized header cannot be injected into the logs or the response headers.

Limitations
-----------
- Duration is wall-clock, measured around the whole request.  It is not a
  latency histogram and no percentile statistics are produced.
- No metrics are exported.  The engine exposes logs and health endpoints only.
- The record factory is process-global.  It adds exactly one attribute and
  delegates to whatever factory was already installed.
"""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar, Token

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

#: Inbound/outbound header carrying the correlation ID.
REQUEST_ID_HEADER = "X-Request-ID"

#: Service name reported on every access-log line.
SERVICE_NAME = "ai-engine"

#: Logger tree this module owns and configures.
LOGGER_NAME = "app"

#: Level used when ``LOG_LEVEL`` is unset or unrecognised.
DEFAULT_LOG_LEVEL = "INFO"

#: Access-log line format.  ``request_id`` is present on every record because
#: the record factory below guarantees it.
LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s [%(name)s] request_id=%(request_id)s %(message)s"
)

#: A caller-supplied correlation ID is honoured only if it is short and made
#: of characters that are safe in both a log line and an HTTP header.
_SAFE_REQUEST_ID = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")

#: Attribute name added to every log record by the record factory.
_REQUEST_ID_ATTR = "request_id"

#: Attribute name used for the generated-ID sentinel on non-HTTP scopes.
_OUT_OF_SCOPE = "-"

_request_id: ContextVar[str] = ContextVar("ai_engine_request_id", default=_OUT_OF_SCOPE)

#: Captured at import time so repeated installation cannot chain factories.
_base_record_factory = logging.getLogRecordFactory()

_installed = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------


def new_request_id() -> str:
    """Return a fresh, opaque correlation ID."""
    return uuid.uuid4().hex


def current_request_id() -> str:
    """Return the correlation ID of the request in scope, or ``"-"``."""
    return _request_id.get()


def resolve_request_id(supplied: str | None) -> str:
    """Return a usable correlation ID for this request.

    *supplied* is the inbound ``X-Request-ID`` header value, if any.  It is
    honoured only when it matches :data:`_SAFE_REQUEST_ID`; anything else —
    including an empty, oversized, or otherwise unexpected value — is replaced
    by a generated ID so the logs and the response header stay well-formed.
    """
    if supplied and _SAFE_REQUEST_ID.match(supplied):
        return supplied
    return new_request_id()


def _install_record_factory() -> None:
    """Stamp the in-scope request ID onto every log record.

    A :mod:`logging` filter cannot do this job: filters attached to a *logger*
    are not consulted while a record propagates, and the handlers that matter
    are configured by ``uvicorn`` and are not ours to reach.  The record
    factory runs for every record regardless of which logger or handler
    produced it, which is the only hook that reliably covers the whole tree.
    """

    def factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = _base_record_factory(*args, **kwargs)
        record.request_id = current_request_id()
        return record

    logging.setLogRecordFactory(factory)


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------


def resolve_log_level(name: str | None) -> int:
    """Map a ``LOG_LEVEL`` string to a :mod:`logging` level.

    Unrecognised values fall back to :data:`DEFAULT_LOG_LEVEL` rather than
    raising, so a typo in the environment cannot stop the service from
    starting or silence its logs.
    """
    if not name:
        return getattr(logging, DEFAULT_LOG_LEVEL)
    level = getattr(logging, name.strip().upper(), None)
    return level if isinstance(level, int) else getattr(logging, DEFAULT_LOG_LEVEL)


def configure_logging(level: int | None = None) -> None:
    """Give the ``app`` logger tree a handler and a level.

    Idempotent: a second call does not add a second handler, so importing the
    application twice (or re-running startup in a test) cannot duplicate every
    log line.  The root logger is deliberately left alone, so this does not
    disturb the server's own logging setup.
    """
    app_logger = logging.getLogger(LOGGER_NAME)
    if not app_logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        app_logger.addHandler(handler)
    if level is not None:
        app_logger.setLevel(level)


# ---------------------------------------------------------------------------
# Access logging
# ---------------------------------------------------------------------------


def classify_outcome(status_code: int) -> str:
    """Return the coarse outcome class for *status_code*.

    The status code itself already distinguishes engine failure (500) from
    provider failure (502), provider unavailability (503), and provider
    timeout (504).  This adds the 2xx / 4xx / 5xx grouping so the common
    "is this request healthy at all" question is answerable without knowing
    every code.
    """
    if status_code < 400:
        return "success"
    if status_code < 500:
        return "client_error"
    return "server_error"


class RequestObservabilityMiddleware:
    """Assign a request ID and emit one access-log line per HTTP request.

    Implemented as plain ASGI rather than through ``@app.middleware("http")``
    so that it runs in the same task as the endpoint it wraps.  A
    ``BaseHTTPMiddleware`` hands the downstream app to a separate task, which
    makes request-scoped :class:`~contextvars.ContextVar` values depend on
    framework version; doing it here keeps the correlation ID visible to the
    route and to the orchestrator unconditionally.

    Non-HTTP scopes (lifespan, WebSocket) pass straight through.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(_header_value(scope, REQUEST_ID_HEADER))
        token: Token[str] = _request_id.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message) -> None:  # type: ignore[no-untyped-def]
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers") or [])
                headers.append(
                    (
                        REQUEST_ID_HEADER.lower().encode("latin-1"),
                        request_id.encode("latin-1"),
                    )
                )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            try:
                # Logged before the context variable is reset so the access
                # line is stamped with this request's ID like any other.
                logger.info(
                    "request completed",
                    extra={
                        "service": SERVICE_NAME,
                        "method": scope.get("method", "-"),
                        # `path` excludes the query string, so no query
                        # parameters are ever logged.
                        "path": scope.get("path", "-"),
                        "status_code": status_code,
                        "outcome": classify_outcome(status_code),
                        "duration_ms": round(duration_ms, 3),
                    },
                )
            finally:
                _request_id.reset(token)


def _header_value(scope, name: str) -> str | None:  # type: ignore[no-untyped-def]
    """Return the raw value of header *name* from an ASGI scope, if present."""
    wanted = name.lower().encode("latin-1")
    for raw_name, raw_value in scope.get("headers") or []:
        if raw_name.lower() == wanted:
            return raw_value.decode("latin-1")
    return None


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install_observability(app, *, level: int | None = None) -> None:
    """Wire correlation, access logging, and log configuration into *app*.

    Idempotent, so importing the application more than once cannot stack
    middlewares or duplicate log handlers.
    """
    global _installed
    if _installed:
        return
    _install_record_factory()
    configure_logging(level)
    app.add_middleware(RequestObservabilityMiddleware)
    _installed = True
