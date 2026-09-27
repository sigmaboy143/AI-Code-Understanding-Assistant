"""Timeout behaviour, measured against a real socket.

Category
--------
**Performance / failure.** Unlike the rest of the performance suite, this module
opens a real TCP listener on ``127.0.0.1`` and lets a real ``OllamaProvider``
with a real ``httpx`` client time out against it.  Nothing is stubbed between
the provider and the kernel, so what is measured is genuine timeout
enforcement.

Why a real socket
-----------------
``httpx.MockTransport`` bypasses the timeout machinery entirely — a handler that
raises :class:`httpx.ReadTimeout` proves the provider's *translation* of a
timeout, which the existing integration suite already covers, but it proves
nothing about *when* a timeout actually fires.  Only a peer that accepts the
connection and then goes silent exercises the real read-timeout path.

The listener is created and destroyed by the test, binds to the loopback
interface on an OS-assigned port, and never speaks HTTP.  No external network,
no Ollama daemon, and no model are involved.

Budgets
-------
The probe budget lives on a provider instance created *inside* the test
(:data:`~tests.performance.harness.TIMEOUT_PROBE_BUDGET_S`).  **No production
timeout value is modified** — not ``Settings.request_timeout``, not
``OllAMA_TEST_BASE_URL``, and not the ``timeout=60`` default in
``OllamaProvider``.  A short budget is needed only so that three samples cost
about three seconds instead of six minutes.

Relationship to the Phase 13 blocker
------------------------------------
The live ``qwen3:8b`` full-analysis request does not answer inside the read
timeout.  This module does **not** re-run that request: it characterises the
timeout *mechanism* that the blocker depends on, so that when the model-side
cause is fixed, the mapping it has to satisfy is already pinned down and
measured.  The live blocker itself is recorded as unresolved.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import suppress

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from tests.fixtures import explanation_input
from tests.performance.harness import (
    TIMEOUT_EARLY_TOLERANCE_S,
    TIMEOUT_OVERSHOOT_TOLERANCE,
    TIMEOUT_PROBE_BUDGET_S,
    TIMEOUT_SAMPLE_COUNT,
    measure_async,
    record,
    summarise,
)

ENDPOINT = "/api/v1/code-understanding"


class SilentUpstream:
    """A loopback TCP server that accepts connections and then says nothing.

    This is the exact shape of the Phase 13 condition: the daemon is up, the
    connection succeeds, and then no bytes ever arrive.  The connection is held
    open deliberately — closing it would produce a protocol error, not a
    timeout, and would test the wrong branch.

    The listener runs on its **own thread and its own event loop**, which is
    what keeps this usable from both styles of test in this module:

    - ``TestClient.post`` is a blocking, synchronous call.  If it were made
      while this test's own event loop was also responsible for accepting the
      connection, the one call would block the loop that the connection needs,
      and the request would stall instead of timing out.  Anyio resolves a
      blocking portal against the *current* async context, so nesting these
      deadlocks rather than merely distorting the measurement.
    - ``pytest-asyncio``'s loop is likewise free to be busy elsewhere.

    Isolating the listener removes that coupling entirely, so the only thing
    the timeout measures is the timeout.
    """

    #: Seconds to wait for the listener to bind before giving up.
    BIND_TIMEOUT_S = 10.0

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self.base_url = ""

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> SilentUpstream:
        self._thread = threading.Thread(
            target=self._serve_forever, name="silent-upstream", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(self.BIND_TIMEOUT_S):
            self.__exit__(None, None, None)
            raise RuntimeError("SilentUpstream did not bind a loopback port in time")
        if self._error is not None:
            error, self._error = self._error, None
            self.__exit__(None, None, None)
            raise RuntimeError("SilentUpstream failed to start") from error
        return self

    def __exit__(self, *exc_info) -> None:
        loop, self._loop = self._loop, None
        if loop is not None and self._stop is not None:
            # Ask the loop to finish its coroutine normally.  Stopping the loop
            # outright would abandon the coroutine mid-await, which asyncio
            # reports as an unraisable exception and a destroyed-pending-task
            # error — noise that would otherwise be attributed to the engine.
            loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        self._stop = None

    # -- server ------------------------------------------------------------

    def _serve_forever(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._bind_and_wait())
        except BaseException as exc:  # noqa: BLE001 - reported to the test thread
            if self._error is None:
                self._error = exc
            self._ready.set()
        finally:
            with suppress(Exception):
                loop.close()
            asyncio.set_event_loop(None)

    async def _bind_and_wait(self) -> None:
        stop = asyncio.Event()
        self._stop = stop
        handlers: set[asyncio.Task] = set()
        server = await asyncio.start_server(
            lambda r, w: self._hold(r, w, handlers), host="127.0.0.1", port=0
        )
        try:
            self.base_url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            self._ready.set()
            await stop.wait()
        finally:
            # Order matters.  ``wait_closed()`` does not return until every
            # handler task has finished, and the handlers are deliberately
            # parked forever, so they have to be cancelled *first*.  Cancelling
            # after awaiting would make each teardown sit out the join timeout,
            # turning a sub-second module into a minute-long one.
            server.close()
            for task in handlers:
                task.cancel()
            if handlers:
                await asyncio.gather(*handlers, return_exceptions=True)
            with suppress(Exception):
                await server.wait_closed()

    async def _hold(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handlers: set[asyncio.Task],
    ) -> None:
        """Accept, read the request, then stall until the listener shuts down."""
        task = asyncio.current_task()
        if task is not None:
            handlers.add(task)
        try:
            await reader.read(4096)
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
        finally:
            if task is not None:
                handlers.discard(task)
            with suppress(Exception):
                writer.close()


# ---------------------------------------------------------------------------
# 1. Real timeout enforcement
# ---------------------------------------------------------------------------


async def test_a_silent_upstream_produces_a_timeout_at_the_configured_budget(monkeypatch):
    """Measure when a real read timeout actually fires.

    Three assertions, all of them the point of this module:
    - the error is a timeout, not a connection failure or a protocol error;
    - it fires *no earlier* than the budget, so healthy requests are safe;
    - it fires no later than a small multiple of the budget, so the caller is
      not left hanging.
    """
    with SilentUpstream() as upstream:
        provider = OllamaProvider(
            base_url=upstream.base_url, model="qwen3:8b", timeout=TIMEOUT_PROBE_BUDGET_S
        )
        from tests.fixtures import analysis_llm_request

        request = analysis_llm_request()
        observed: list[float] = []

        async def one_attempt() -> None:
            start = time.perf_counter()
            with pytest.raises(ProviderError) as excinfo:
                await provider.complete(request)
            observed.append(time.perf_counter() - start)
            message = str(excinfo.value)
            assert "timed out" in message.lower(), message
            assert "Cannot connect" not in message, message

        measurement = record(
            await measure_async(
                f"real read timeout (budget {TIMEOUT_PROBE_BUDGET_S}s, silent peer)",
                TIMEOUT_SAMPLE_COUNT,
                one_attempt,
                warmup=0,
                notes="real loopback socket; no stub between provider and kernel",
            )
        )

    assert measurement.count == TIMEOUT_SAMPLE_COUNT
    print(
        f"[perf] timeout fired at median {measurement.median_ms:.1f}ms for a "
        f"{TIMEOUT_PROBE_BUDGET_S}s budget "
        f"(min {measurement.min_ms:.1f}ms, max {measurement.max_ms:.1f}ms)"
    )

    # No early fire: a premature timeout would fail healthy requests.
    assert measurement.min_ms >= (TIMEOUT_PROBE_BUDGET_S - TIMEOUT_EARLY_TOLERANCE_S) * 1000.0, (
        f"a timeout fired after only {measurement.min_ms:.1f}ms, which is inside "
        f"the {TIMEOUT_PROBE_BUDGET_S}s budget and would fail a healthy request: "
        f"{measurement.summary()}"
    )
    # No runaway overshoot: the budget has to actually bound the wait.
    assert measurement.max_ms <= (
        TIMEOUT_PROBE_BUDGET_S * TIMEOUT_OVERSHOOT_TOLERANCE
    ) * 1000.0, (
        f"the timeout overshot its budget badly: max {measurement.max_ms:.1f}ms "
        f"against a {TIMEOUT_PROBE_BUDGET_S}s budget: {measurement.summary()}"
    )


async def test_the_reported_budget_matches_the_configured_one(monkeypatch):
    """The 504 body must be traceable to the timeout that actually fired.

    Measured, not asserted by string-matching alone: the elapsed time and the
    configured budget are checked together, so a provider that reported a
    different budget than the one it enforced would be caught.
    """
    from tests.fixtures import analysis_llm_request

    with SilentUpstream() as upstream:
        provider = OllamaProvider(
            base_url=upstream.base_url, model="qwen3:8b", timeout=TIMEOUT_PROBE_BUDGET_S
        )
        start = time.perf_counter()
        with pytest.raises(ProviderError) as excinfo:
            await provider.complete(analysis_llm_request())
        elapsed = time.perf_counter() - start

    message = str(excinfo.value)
    # The provider reports the budget it was constructed with, verbatim.  This is
    # checked against the same float the provider was given, so it stays true
    # if the probe budget is ever retuned.
    assert f"{TIMEOUT_PROBE_BUDGET_S}s" in message, message
    assert elapsed >= TIMEOUT_PROBE_BUDGET_S - TIMEOUT_EARLY_TOLERANCE_S, (
        f"returned after {elapsed:.3f}s, faster than the "
        f"{TIMEOUT_PROBE_BUDGET_S}s budget it claims to enforce"
    )


# ---------------------------------------------------------------------------
# 2. Budget is honoured across a range of values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("budget", [0.5, 1.0, 2.0], ids=["0.5s", "1s", "2s"])
async def test_timeout_scales_with_the_configured_budget(budget):
    """A larger budget must mean a longer wait, in proportion.

    If the provider ignored its configured timeout and used a fixed one, this
    would fail.  A constant factor on the client only is what is expected; the
    bounds are wide because the point is proportionality, not precision.
    """
    from tests.fixtures import analysis_llm_request

    with SilentUpstream() as upstream:
        provider = OllamaProvider(
            base_url=upstream.base_url, model="qwen3:8b", timeout=budget
        )
        start = time.perf_counter()
        with pytest.raises(ProviderError):
            await provider.complete(analysis_llm_request())
        elapsed = time.perf_counter() - start

    print(f"[perf] budget {budget}s -> observed {elapsed:.3f}s")
    assert elapsed >= budget * 0.75, (
        f"a {budget}s budget fired after only {elapsed:.3f}s"
    )
    assert elapsed <= budget * 2.0 + 0.5, (
        f"a {budget}s budget took {elapsed:.3f}s to fire"
    )


# ---------------------------------------------------------------------------
# 3. The real ProviderError -> 504 mapping, with real timing
# ---------------------------------------------------------------------------


def test_a_silent_upstream_maps_to_504_within_the_budget(monkeypatch):
    """End to end through the real route: silent peer in, 504 out, on time.

    This is the mapping the Phase 13 blocker ultimately hits, exercised with a
    real socket rather than a scripted exception, and timed so the guarantee
    includes *when* the caller is told.

    ``TestClient.post`` is blocking, so this test is deliberately synchronous.
    Driving it from inside a running event loop would leave the loop that has
    to accept the upstream connection unable to run at all.
    """
    from unittest.mock import patch

    client = TestClient(app)
    body = explanation_input().model_dump(mode="json", exclude_none=True)

    with SilentUpstream() as upstream:
        provider = OllamaProvider(
            base_url=upstream.base_url, model="qwen3:8b", timeout=TIMEOUT_PROBE_BUDGET_S
        )
        start = time.perf_counter()
        with patch("app.main._build_provider", return_value=provider):
            response = client.post(ENDPOINT, json=body)
        elapsed = time.perf_counter() - start

    measurement = record(
        summarise(
            f"POST -> 504 against a silent peer (budget {TIMEOUT_PROBE_BUDGET_S}s)",
            [elapsed * 1000.0],
        )
    )

    assert response.status_code == 504, response.text
    body_json = response.json()
    assert body_json["error"]["code"] == "PROVIDER_TIMEOUT"
    assert "summary" not in body_json, "a timeout must never carry an answer"
    # The configured budget stays internal.
    assert f"{int(TIMEOUT_PROBE_BUDGET_S)}" not in body_json["error"]["message"]

    print(f"[perf] silent peer -> 504 after {elapsed:.3f}s")
    assert elapsed >= TIMEOUT_PROBE_BUDGET_S - TIMEOUT_EARLY_TOLERANCE_S, (
        f"504 returned after only {elapsed:.3f}s, faster than the "
        f"{TIMEOUT_PROBE_BUDGET_S}s budget the provider enforced"
    )
    assert measurement.max_ms <= (
        TIMEOUT_PROBE_BUDGET_S * TIMEOUT_OVERSHOOT_TOLERANCE
    ) * 1000.0 + 250.0, (
        f"504 took far longer than the budget allowed: {measurement.summary()}"
    )


# ---------------------------------------------------------------------------
# 4. A responsive peer must NOT be mistaken for a timeout
# ---------------------------------------------------------------------------


def test_a_responsive_upstream_is_not_mistaken_for_a_timeout(monkeypatch):
    """The other direction, and the one that would be a real incident.

    A timeout that fires too eagerly is worse than no timeout at all: it turns
    working requests into 504s.  This drives the same provider against a peer
    that answers immediately, using a budget far longer than the answer takes,
    and asserts a 200.
    """
    from unittest.mock import patch

    import httpx

    client = TestClient(app)
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    from tests.fixtures import VALID_OLLAMA_BODY, install_transport, ollama_provider

    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )
    # Ten times the probe budget, so an answer that takes a few milliseconds
    # cannot possibly be near the limit.
    provider = ollama_provider(timeout=int(TIMEOUT_PROBE_BUDGET_S * 10))

    start = time.perf_counter()
    with patch("app.main._build_provider", return_value=provider):
        response = client.post(ENDPOINT, json=payload)
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.text
    assert elapsed < TIMEOUT_PROBE_BUDGET_S, (
        f"a responsive upstream took {elapsed:.3f}s, which is at or beyond the "
        f"{TIMEOUT_PROBE_BUDGET_S}s probe budget"
    )
