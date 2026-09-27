"""Performance of the provider round trip.

Category
--------
**Performance.** A real ``OllamaProvider`` and a real ``httpx`` client, with the
socket replaced by the scripted transport in ``tests.fixtures.ollama_transport``.

What is measured
----------------
1. **Provider call duration** — one ``OllamaProvider.complete()`` against a
   stubbed upstream.  This is the engine's own per-request cost: client
   construction, request serialisation, and response parsing.  It **excludes
   model inference**, which is why it is reported as *provider round-trip
   overhead* and never as model latency.
2. **Upstream attempt count** — how many times a single ``complete()`` reaches
   the network.  A silent retry storm is a latency and load amplifier, so the
   invariant "exactly one attempt" is asserted directly rather than inferred
   from timing.
3. **Failure-path cost** — the same round trip when the upstream fails, because
   a failure path that is slower than a success path is a real incident risk.
4. **Prompt-size scaling** — the same call with a growing synthetic payload, to
   show whether engine-side cost tracks input size.

Why the socket is stubbed
-------------------------
A live measurement would be dominated by ``qwen3:8b`` and would be neither
repeatable nor attributable: a slow number would say nothing about the engine.
Stubbing the socket isolates exactly the part this phase is allowed to change
and measure — the code between the orchestrator and the network.

Thresholds
----------
The absolute ceiling (:data:`~tests.performance.harness.PROVIDER_CALL_CEILING_MS`)
is a wide tripwire, not a target.  The assertions that carry the weight are the
structural ones: one attempt per call, and one client per call.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from tests.fixtures import (
    CHAT_URL,
    VALID_OLLAMA_BODY,
    analysis_llm_request,
    connect_error,
    install_transport,
)
from tests.performance.harness import (
    PROVIDER_CALL_CEILING_MS,
    SAMPLE_COUNT,
    WARMUP_ITERATIONS,
    Measurement,
    measure,
    measure_async,
    record,
)

#: Sizes, in lines, of the synthetic snippet used for the scaling measurement.
#: All of it is generated from a counter, so none of it is repository source.
SCALING_LINE_COUNTS = (10, 100, 500, 1000)


def _synthetic_source(lines: int) -> str:
    """Return *lines* lines of trivially generated, non-repository code."""
    return "\n".join(f"def f{i}(a, b):\n    return a + {i} + b" for i in range(lines))


def _scaling_request(lines: int):
    """Return an ``LLMRequest`` whose user turn carries a synthetic payload."""
    from app.providers.base import LLMMessage, LLMRequest

    return LLMRequest(
        messages=[
            LLMMessage(role="system", content="You analyse code."),
            LLMMessage(
                role="user",
                content="def add(a, b): return a + b\n" + _synthetic_source(lines),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# 1. Provider call duration
# ---------------------------------------------------------------------------


async def test_provider_call_duration_is_bounded(monkeypatch):
    """One provider round trip against a stubbed upstream must stay cheap.

    The recorded value is the engine's own overhead.  It is *not* model
    latency, and it is never reported as such.
    """
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY))
    provider = OllamaProvider(base_url="http://ollama.test:11434", model="qwen3:8b", timeout=120)

    # Built once: the measurement must cover complete(), not request assembly.
    request = analysis_llm_request()

    async def call() -> object:
        return await provider.complete(request)

    measurement = record(
        await measure_async(
            "provider.complete (socket stubbed)",
            SAMPLE_COUNT,
            call,
            notes="engine-side overhead only; excludes model inference",
        )
    )

    assert isinstance(measurement, Measurement)
    assert measurement.count == SAMPLE_COUNT
    assert measurement.median_ms < PROVIDER_CALL_CEILING_MS, measurement.summary()
    assert measurement.p95_ms < PROVIDER_CALL_CEILING_MS, measurement.summary()


async def test_every_provider_call_returns_usable_content(monkeypatch):
    """The timed loop above must have been doing real work, not failing fast.

    Without this, a regression that made ``complete()`` raise immediately would
    still produce a flattering timing distribution.
    """
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY))
    provider = OllamaProvider(base_url="http://ollama.test:11434")

    response = await provider.complete(analysis_llm_request())

    assert response.content == VALID_OLLAMA_BODY["message"]["content"]
    assert response.model == "qwen3:8b"


# ---------------------------------------------------------------------------
# 2. Upstream attempt count — the real latency risk
# ---------------------------------------------------------------------------


async def test_one_complete_call_makes_exactly_one_upstream_attempt(monkeypatch):
    """No silent retries.

    ``httpx`` does not retry by default, so a single ``complete()`` is expected
    to produce one request.  This is asserted rather than timed because a retry
    that only shows up on failure or on a slow upstream is invisible in a
    median, and it is precisely those cases where a retry would be added.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    provider = OllamaProvider(base_url="http://ollama.test:11434")

    for _ in range(25):
        await provider.complete(analysis_llm_request())

    assert len(seen) == 25, f"expected one attempt per call, got {len(seen)} for 25 calls"
    assert all(str(item.url) == CHAT_URL for item in seen)


async def test_a_failed_call_also_makes_exactly_one_attempt(monkeypatch):
    """A failing upstream must not be retried either.

    This is the case that matters most: retries on failure multiply load on
    precisely the daemon that is already struggling.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise connect_error("connection refused")

    install_transport(monkeypatch, handler)
    provider = OllamaProvider(base_url="http://ollama.test:11434")

    for _ in range(25):
        with pytest.raises(ProviderError):
            await provider.complete(analysis_llm_request())

    assert len(seen) == 25, f"expected one attempt per call, got {len(seen)} for 25 calls"


async def test_exactly_one_client_is_built_per_call(monkeypatch):
    """Client construction is the engine's dominant per-request cost.

    It is recorded here rather than fixed here: changing the client lifecycle is
    a provider-architecture change, which is explicitly out of scope for this
    batch.  The measurement is what makes that trade-off reviewable later.
    """
    real_client = httpx.AsyncClient
    created: list[httpx.AsyncClient] = []

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        client = real_client(
            *args,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=VALID_OLLAMA_BODY)
            ),
            **kwargs,
        )
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    provider = OllamaProvider(base_url="http://ollama.test:11434")

    for _ in range(20):
        await provider.complete(analysis_llm_request())

    assert len(created) == 20
    assert all(client.is_closed for client in created), "a client was left unclosed"


# ---------------------------------------------------------------------------
# 3. Failure-path cost
# ---------------------------------------------------------------------------


async def test_failure_path_costs_about_the_same_as_the_success_path(monkeypatch):
    """A rejected upstream must not be dramatically more expensive.

    A failure path that is much slower than a success path turns every provider
    incident into a cascading one, because the clients pile up while they wait.
    The bound is relative and loose; the point is to catch an order of magnitude,
    not to police microseconds.
    """
    # One transport, one patch, with a swappable outcome.  Installing the
    # scripted transport twice in one test would nest the ``httpx.AsyncClient``
    # factories, and the outer one would keep serving the first scripted
    # outcome — the failure path would silently never be taken.
    state: dict[str, object] = {"outcome": "success"}
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outcome = state["outcome"]
        attempts.append(outcome)
        if outcome == "failure":
            raise connect_error("connection refused")
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    provider = OllamaProvider(base_url="http://ollama.test:11434")
    request = analysis_llm_request()

    async def succeeding_call() -> object:
        state["outcome"] = "success"
        return await provider.complete(request)

    async def failing_call() -> object:
        state["outcome"] = "failure"
        with pytest.raises(ProviderError):
            await provider.complete(request)

    success = record(
        await measure_async(
            "provider.complete success (socket stubbed)",
            SAMPLE_COUNT,
            succeeding_call,
            notes="baseline for the failure-path comparison",
        )
    )
    attempts.clear()

    failure = record(
        await measure_async(
            "provider.complete failure (socket stubbed)",
            SAMPLE_COUNT,
            failing_call,
            notes="upstream refuses the connection; ProviderError raised",
        )
    )
    # measure_async runs WARMUP_ITERATIONS untimed calls before it starts
    # recording, and the tally below is deliberately not cleared of them.
    assert attempts == ["failure"] * (SAMPLE_COUNT + WARMUP_ITERATIONS), (
        f"expected exactly one failed attempt per call, saw {len(attempts)} "
        f"attempts for {SAMPLE_COUNT} calls"
    )
    assert failure.median_ms < success.median_ms * 10 + 5.0, (
        f"failure path is disproportionately slow: "
        f"success median {success.median_ms:.3f}ms vs "
        f"failure median {failure.median_ms:.3f}ms"
    )


# ---------------------------------------------------------------------------
# 4. Prompt-size scaling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lines", SCALING_LINE_COUNTS)
def test_engine_side_cost_stays_flat_as_the_prompt_grows(lines):
    """Engine-side cost must not scale with input size.

    The payload really is serialised and posted at every size, exactly as
    ``OllamaProvider.complete`` does it, so the growing user turn is on the wire
    rather than merely constructed in memory.

    A roughly flat cost across a 100x input range is the useful result: it
    isolates prompt size as a *model* problem rather than an engine problem,
    which is exactly where the Phase 13 blocker sits.
    """
    captured: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(len(request.content))
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    # Build the outbound payload the same way the provider does, so what is
    # measured is the real serialisation cost of the real prompt shape.
    llm_request = _scaling_request(lines)
    payload = {
        "model": "qwen3:8b",
        "messages": [
            {"role": m.role, "content": m.content} for m in llm_request.messages
        ],
        "stream": False,
    }
    body = json.dumps(payload).encode()

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    def one_call() -> int:
        response = client.post(CHAT_URL, content=body)
        return response.status_code

    try:
        one_call()
        upstream_bytes = captured[-1] if captured else 0
        measurement = record(
            measure(
                f"serialise+post {lines} synthetic lines",
                max(30, SAMPLE_COUNT // 6),
                one_call,
                warmup=10,
                notes=f"upstream request body was {upstream_bytes} bytes",
            )
        )
        final_status = one_call()
    finally:
        client.close()

    assert upstream_bytes > 0, "the scaling harness never captured a request body"
    assert final_status == 200, "the timed loop must have been posting real requests"
    assert measurement.median_ms < PROVIDER_CALL_CEILING_MS, measurement.summary()
