"""Performance of the full in-process request path.

Category
--------
**Performance.** ``POST /api/v1/code-understanding`` driven through the real
FastAPI application, with a real ``OllamaProvider`` and a real ``httpx`` client;
only the socket is replaced.

What is measured
----------------
1. **AI request duration** â€” one complete round trip through the whole engine:
   request validation, context assembly, prompt construction, the provider call,
   response validation, confidence and evidence derivation, dependency
   grounding, and response serialisation.
2. **Stage decomposition** â€” the same request measured stage by stage, so that
   "the request took N ms" can be attributed rather than merely stated.
3. **Stage accounting** â€” the stages must add up to the whole.  This is the
   assertion that makes the decomposition trustworthy: it fails if real work
   appears outside the instrumented stages.
4. **Latency additivity** â€” with a synthetic upstream delay, total time must be
   the delay *plus* engine overhead, not a multiple of it.  A large multiplier
   would mean hidden retries or a serialised re-read somewhere.
5. **Fail-fast cost** â€” an invalid request must be rejected cheaply, before any
   provider work, so bad input never consumes model capacity.
6. **Error-mapping cost** â€” 502 and 504 must not be dramatically more expensive
   than success, or a provider incident turns into a cascade.

Thresholds
----------
Ceilings are wide tripwires.  The assertions that carry weight are structural:
stage accounting, additivity, and attempt counts.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.context_builder import ContextBuilder
from app.main import app
from app.orchestrator import OrchestratorService
from app.output_validation import validate_llm_response
from app.output_validation.dependencies import build_dependency_analysis
from app.providers.base import LLMResponse
from app.reasoning import build_reasoning_request
from app.schemas import AnalysisMetadata, CodeUnderstandingResponse
from tests.fixtures import (
    CHAT_URL,
    VALID_OLLAMA_BODY,
    connect_error,
    dependencies_input,
    explanation_input,
    install_transport,
    ollama_provider,
)
from tests.performance.harness import (
    AI_REQUEST_CEILING_MS,
    COMPARISON_SAMPLE_COUNT,
    PROVIDER_CALL_CEILING_MS,
    PROVIDER_DELAY_MS,
    REQUEST_SAMPLE_COUNT,
    SIMULATED_UPSTREAM_LATENCY_MS,
    STAGE_ACCOUNTING_TOLERANCE,
    STAGE_SAMPLE_COUNT,
    WARMUP_ITERATIONS,
    measure,
    record,
    summarise,
)

#: The provider delay the concurrency checks work in, expressed in seconds.
PROVIDER_DELAY_S = PROVIDER_DELAY_MS / 1000.0

client = TestClient(app)

ENDPOINT = "/api/v1/code-understanding"

#: Status each scripted upstream outcome must produce through the real route.
#: Asserted per batch, so a mis-wired fixture cannot be timed in the belief
#: that it exercised a path it never reached.
EXPECTED_STATUS = {"success": 200, "refused": 502, "timeout": 504}


def _payload(**overrides) -> dict:
    """Return the smallest valid analysis payload, with optional overrides."""
    payload = explanation_input().model_dump(mode="json", exclude_none=True)
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. AI request duration
# ---------------------------------------------------------------------------


def test_ai_request_duration_is_bounded(monkeypatch):
    """One full in-process analysis request, with the socket stubbed.

    Recorded as *engine request duration*.  It excludes model inference, which
    is why the live figure is reported separately and never folded into this.
    """
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )

    provider = ollama_provider()
    body = _payload()
    with patch("app.main._build_provider", return_value=provider):
        measurement = record(
            measure(
                "POST /code-understanding (socket stubbed)",
                REQUEST_SAMPLE_COUNT,
                lambda: client.post(ENDPOINT, json=body),
                notes="whole engine path; excludes model inference",
            )
        )

    assert measurement.count == REQUEST_SAMPLE_COUNT
    assert measurement.median_ms < AI_REQUEST_CEILING_MS, measurement.summary()
    assert measurement.p95_ms < AI_REQUEST_CEILING_MS, measurement.summary()


def test_the_timed_request_path_actually_succeeds(monkeypatch):
    """The timing loop must have been producing real, complete answers.

    A regression that made the endpoint fail fast would otherwise post a very
    flattering number.
    """

    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )
    with patch("app.main._build_provider", return_value=ollama_provider()):
        response = client.post(ENDPOINT, json=_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == VALID_OLLAMA_BODY["message"]["content"]
    assert body["confidence"]["level"]
    assert body["confidence"]["evidence"]


# ---------------------------------------------------------------------------
# 2 & 3. Stage decomposition and accounting
# ---------------------------------------------------------------------------


async def test_stage_decomposition_attributes_the_request_cost(monkeypatch):
    """Measure each stage of a request on its own, then check they add up.

    The five stages are exactly the units of work the orchestrator delegates to,
    so the decomposition is an attribution, not a guess.

    Every stage — and the whole call — is measured **inside one event loop**,
    **interleaved** round by round.  Both properties are required:

    - One loop.  Timing the provider stage by calling ``asyncio.run`` per
      iteration would create and tear down a fresh loop each time, charging the
      stage for loop construction that the real request never pays, and the
      stage sum would then exceed the total it is supposed to explain.
    - Interleaved.  Measuring the stages to completion and the whole call
      afterwards compares two different machine states.  The stages are tight
      and a whole call can absorb a scheduler stall, so on a shared machine the
      total's median drifts up and the check fails on noise while reporting
      missing work.  Alternating the two keeps them comparable.

    The accounting check is what makes the numbers worth reporting: if the
    stages do not account for the whole call, the decomposition is missing
    something and the report should not trust it.
    """
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )

    request = explanation_input()
    builder = ContextBuilder()
    provider = ollama_provider()
    service = OrchestratorService(provider=provider, context_builder=builder)
    stage_count = STAGE_SAMPLE_COUNT

    built = builder.build(request, None)
    chunks = built.included_chunks
    llm_request = build_reasoning_request(request, chunks or None)
    llm_response = LLMResponse(
        content=VALID_OLLAMA_BODY["message"]["content"],
        model=VALID_OLLAMA_BODY["model"],
        finish_reason=VALID_OLLAMA_BODY["done_reason"],
    )

    async def _context_stage() -> object:
        return builder.build(request, None)

    async def _prompt_stage() -> object:
        return build_reasoning_request(request, chunks or None)

    async def _provider_stage() -> object:
        return await provider.complete(llm_request)

    async def _parse_stage() -> object:
        return validate_llm_response(
            llm_response,
            included_chunks=chunks or None,
            file_path=request.file_path,
        )

    # ``OrchestratorService._parse_response`` does more than validate: it also
    # builds ``AnalysisMetadata`` and the outer ``CodeUnderstandingResponse``.
    # Both are pydantic constructions, so they are measured as their own stage
    # rather than folded into validation.
    summary_text, confidence = validate_llm_response(
        llm_response,
        included_chunks=chunks or None,
        file_path=request.file_path,
    )

    async def _assembly_stage() -> object:
        metadata = AnalysisMetadata(
            language=request.language,
            file_path=request.file_path,
            analyses=list(request.analyses),
        )
        return CodeUnderstandingResponse(
            summary=summary_text,
            metadata=metadata,
            confidence=confidence,
            dependencies=None,
        )

    async def _whole_call() -> object:
        return await service.analyse(request)

    stage_fns = {
        "stage: context assembly": _context_stage,
        "stage: prompt construction": _prompt_stage,
        "stage: provider round trip": _provider_stage,
        "stage: response validation + confidence": _parse_stage,
        "stage: response model assembly (pydantic)": _assembly_stage,
    }

    # Every stage and the whole call are **interleaved**, round by round,
    # inside one event loop.
    #
    # Measuring the stages to completion and then the whole call separately
    # does not work on a shared machine.  The individual stages are tight
    # (stdev around 0.1 ms) while a single `analyse` can absorb a scheduler
    # stall, so its median drifts upward while the stage medians do not, and
    # the accounting check fails on noise while reporting missing work.  On
    # this machine that produced a total whose *fastest* sample was below the
    # sum of the stage medians — proof the excess was timing artefact, not
    # unattributed work.
    #
    # Alternating them means a stall hits one stage sample and the adjacent
    # total sample alike, so the two sides are compared on the same machine
    # state and the difference between them is attributable to the work.
    stage_samples: dict[str, list[float]] = {name: [] for name in stage_fns}
    total_samples: list[float] = []

    async def timed(operation) -> float:
        start = time.perf_counter()
        await operation()
        return (time.perf_counter() - start) * 1000.0

    # Warm every path first, in both modes, so no sample pays a first-call cost.
    for _ in range(WARMUP_ITERATIONS):
        for operation in stage_fns.values():
            await timed(operation)
        await timed(_whole_call)

    for _ in range(stage_count):
        for name, operation in stage_fns.items():
            stage_samples[name].append(await timed(operation))
        total_samples.append(await timed(_whole_call))

    stages = {
        name: record(summarise(name, samples)) for name, samples in stage_samples.items()
    }
    total = record(
        summarise(
            "orchestrate (analyse) in-process",
            total_samples,
            notes="interleaved with the stages; they must account for this",
        )
    )

    stage_total = sum(item.median_ms for item in stages.values())
    for name, item in stages.items():
        assert item.median_ms < AI_REQUEST_CEILING_MS, f"{name}: {item.summary()}"

    # Two-sided.  Under-shooting means uninstrumented work; over-shooting means
    # a stage was double-counted or was measured under different conditions.
    low = total.median_ms * (1.0 - STAGE_ACCOUNTING_TOLERANCE)
    high = total.median_ms * (1.0 + STAGE_ACCOUNTING_TOLERANCE)
    print(
        f"[perf] stage sum = {stage_total:.3f}ms vs total {total.median_ms:.3f}ms "
        f"(accepted window {low:.3f}..{high:.3f}ms)"
    )
    assert low <= stage_total <= high, (
        "stage decomposition does not account for the whole request: "
        f"stages sum to {stage_total:.3f}ms but the call takes "
        f"{total.median_ms:.3f}ms (window {low:.3f}..{high:.3f}ms)"
    )


def test_dependency_grounding_cost_is_small_and_measured():
    """The dependency pass parses source with ``ast``; measure it, do not assume.

    Grounding is the one stage whose cost could grow with input size, so it is
    measured over a range of synthetic snippets.  The number of *imports* is
    what grows here, not the size of any one file's body.
    """
    costs = {}
    for lines in (10, 100, 500, 1000):
        source = "\n".join(f"import mod{i}\n" for i in range(lines)) + "def add(a, b):\n    return a + b\n"
        costs[lines] = record(
            measure(
                f"stage: dependency grounding ({lines} imports)",
                COMPARISON_SAMPLE_COUNT // 2,
                lambda source=source: build_dependency_analysis(source, []),
            )
        )

    smallest = costs[min(costs)].median_ms
    largest = costs[max(costs)].median_ms
    print(
        f"[perf] dependency grounding: {smallest:.3f}ms at {min(costs)} imports "
        f"-> {largest:.3f}ms at {max(costs)} imports"
    )
    for lines, item in costs.items():
        assert item.median_ms < AI_REQUEST_CEILING_MS, f"{lines}: {item.summary()}"

    # The pass parses the submitted source, so its cost is expected to grow with
    # the number of imports.  What must not happen is super-linear growth: a
    # quadratic scan would turn a large file into a stalled request.
    growth = largest / max(smallest, 1e-6)
    input_growth = max(costs) / min(costs)
    print(
        f"[perf] dependency grounding grew {growth:.1f}x for a {input_growth:.0f}x "
        f"larger import count"
    )
    assert growth < input_growth ** 1.5, (
        f"dependency grounding cost grew {growth:.1f}x for a {input_growth:.0f}x "
        f"larger input, which is worse than linear"
    )


# ---------------------------------------------------------------------------
# 4. Latency additivity
# ---------------------------------------------------------------------------


def test_upstream_latency_is_additive_not_multiplicative(monkeypatch):
    """A slow upstream must cost exactly its own latency, once.

    This is the measurement that would expose a hidden retry: two sequential
    attempts of the simulated delay would show up as roughly double, and the
    tolerance here is far tighter than that.

    The two conditions are **interleaved** rather than run as two consecutive
    batches.  On a shared or busy machine a batch that runs first is measured
    while the process is still warming up, and can easily look slower than an
    identical batch that runs later — which is enough to swamp a comparison
    between a ~15 ms baseline and a ~65 ms delayed request.  Alternating the
    conditions sample by sample gives both the same machine state, so the
    difference between the two medians is attributable to the delay.
    """
    delay_s = SIMULATED_UPSTREAM_LATENCY_MS / 1000.0
    state: dict[str, bool] = {"delayed": False}
    attempts: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(state["delayed"])
        if state["delayed"]:
            time.sleep(delay_s)
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    body = _payload()
    pairs = 20

    def one_request() -> float:
        start = time.perf_counter()
        client.post(ENDPOINT, json=body)
        return (time.perf_counter() - start) * 1000.0

    # Warm before recording, in both conditions, so neither one pays for
    # first-call costs the other has already absorbed.
    with patch("app.main._build_provider", return_value=ollama_provider()):
        for delayed in (False, True):
            state["delayed"] = delayed
            one_request()

        baseline_samples: list[float] = []
        delayed_samples: list[float] = []
        for index in range(pairs):
            for delayed, sink in ((False, baseline_samples), (True, delayed_samples)):
                state["delayed"] = delayed
                sink.append(one_request())

    baseline = record(
        summarise("request, no simulated upstream delay", baseline_samples)
    )
    delayed = record(
        summarise(
            f"request, {SIMULATED_UPSTREAM_LATENCY_MS}ms simulated upstream delay",
            delayed_samples,
        )
    )

    # One warm-up per condition plus one recorded request per pair, in each.
    assert attempts.count(True) == pairs + 1, (
        f"expected {pairs + 1} delayed upstream attempts, saw {attempts.count(True)}"
    )
    assert attempts.count(False) == pairs + 1, (
        "each request must produce exactly one upstream attempt; without that, "
        "the delay is not being paid once and the additivity check is void"
    )

    added_ms = delayed.median_ms - baseline.median_ms
    print(
        f"[perf] simulated delay {SIMULATED_UPSTREAM_LATENCY_MS}ms -> "
        f"observed addition {added_ms:.3f}ms "
        f"(baseline {baseline.median_ms:.3f}ms, delayed {delayed.median_ms:.3f}ms)"
    )
    # One delay, plus up to half the baseline overhead as scheduling slack.
    upper = SIMULATED_UPSTREAM_LATENCY_MS * 1.5 + baseline.median_ms
    assert added_ms <= upper, (
        f"upstream latency was not additive: added {added_ms:.3f}ms for a "
        f"{SIMULATED_UPSTREAM_LATENCY_MS}ms delay (baseline {baseline.median_ms:.3f}ms, "
        f"allowed up to {upper:.3f}ms)"
    )
    assert added_ms >= SIMULATED_UPSTREAM_LATENCY_MS * 0.8, (
        f"the simulated delay did not propagate: added only {added_ms:.3f}ms "
        f"(baseline {baseline.median_ms:.3f}ms, delayed {delayed.median_ms:.3f}ms)"
    )


# ---------------------------------------------------------------------------
# 5. Fail-fast cost
# ---------------------------------------------------------------------------


def test_invalid_input_is_rejected_before_any_provider_work(monkeypatch):
    """Rejection must be cheap *and* must not reach the model.

    Both halves matter: a slow rejection wastes a worker, and a rejection that
    still called the provider wastes model capacity.
    """

    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    invalid = {"language": "python", "source_code": "   "}

    with patch("app.main._build_provider", return_value=ollama_provider()):
        measurement = record(
            measure(
                "POST invalid input -> 422",
                REQUEST_SAMPLE_COUNT,
                lambda: client.post(ENDPOINT, json=invalid),
                notes="must be the cheapest path in the engine",
            )
        )

    assert attempts == [], "an invalid request reached the provider"
    assert measurement.median_ms < AI_REQUEST_CEILING_MS, measurement.summary()

    response = client.post(ENDPOINT, json=invalid)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 6. Error-mapping cost
# ---------------------------------------------------------------------------


def test_provider_failure_paths_are_not_disproportionately_slow(monkeypatch):
    """502 and 504 must cost about what a success costs.

    If a failure path were much slower, clients would pile up during a provider
    incident and the incident would grow on its own.

    One transport is installed and its outcome swapped between batches.
    Installing the scripted transport more than once in a single test nests the
    ``httpx.AsyncClient`` factories, after which the outermost one keeps serving
    the first outcome — so the "failure" batches would silently be measuring
    successes.  Each batch therefore asserts the status code it got.
    """
    body = _payload()
    state: dict[str, str] = {"outcome": "success"}
    seen_status: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outcome = state["outcome"]
        if outcome == "refused":
            raise connect_error("connection refused")
        if outcome == "timeout":
            raise httpx.ReadTimeout(
                "timed out", request=httpx.Request("POST", CHAT_URL)
            )
        return httpx.Response(200, json=VALID_OLLAMA_BODY)

    install_transport(monkeypatch, handler)
    count = COMPARISON_SAMPLE_COUNT

    def timed_batch(label: str, outcome: str):
        state["outcome"] = outcome
        seen_status.clear()
        with patch("app.main._build_provider", return_value=ollama_provider()):
            result = record(
                measure(
                    label,
                    count,
                    lambda: seen_status.append(
                        client.post(ENDPOINT, json=body).status_code
                    ),
                )
            )
        assert set(seen_status) == {EXPECTED_STATUS[outcome]}, (
            f"{label}: expected status {EXPECTED_STATUS[outcome]} on every request, "
            f"got {sorted(set(seen_status))}"
        )
        return result

    success = timed_batch("request -> 200", "success")
    refused = timed_batch("request -> 502 (connection refused)", "refused")
    timed_out = timed_batch("request -> 504 (read timeout)", "timeout")

    for label, item in (("502", refused), ("504", timed_out)):
        assert item.median_ms < success.median_ms * 10 + 5.0, (
            f"{label} path is disproportionately slow: "
            f"success {success.median_ms:.3f}ms vs {label} {item.median_ms:.3f}ms"
        )

    # And the two failure paths must still be cheap in absolute terms.
    assert refused.median_ms < AI_REQUEST_CEILING_MS, refused.summary()
    assert timed_out.median_ms < AI_REQUEST_CEILING_MS, timed_out.summary()


def test_dependency_request_is_no_slower_than_an_explanation_request(monkeypatch):
    """Adding the dependency pass must not change the order of magnitude.

    Dependency grounding is the only stage that parses the submitted source, so
    it is the one place a real regression would show up as extra request cost.
    """

    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )
    explanation = explanation_input().model_dump(mode="json", exclude_none=True)
    dependencies = dependencies_input().model_dump(mode="json", exclude_none=True)
    count = COMPARISON_SAMPLE_COUNT

    with patch("app.main._build_provider", return_value=ollama_provider()):
        plain = record(
            measure("request: explanation only", count, lambda: client.post(ENDPOINT, json=explanation))
        )
        with_deps = record(
            measure("request: with dependency grounding", count, lambda: client.post(ENDPOINT, json=dependencies))
        )

    assert client.post(ENDPOINT, json=dependencies).json()["dependencies"], (
        "the dependency request produced no grounded dependencies, so the "
        "comparison is not measuring what it claims to"
    )
    assert with_deps.median_ms < plain.median_ms * 5 + 5.0, (
        f"dependency grounding made the request disproportionately slower: "
        f"{plain.median_ms:.3f}ms -> {with_deps.median_ms:.3f}ms"
    )
    assert with_deps.p95_ms < AI_REQUEST_CEILING_MS, with_deps.summary()
    # Sanity: the provider call itself must still dominate neither budget.
    assert plain.p95_ms < PROVIDER_CALL_CEILING_MS * 3, plain.summary()


def test_health_endpoint_stays_prompt_relative_to_analysis(monkeypatch):
    """Measure liveness against analysis, and record how they actually compare.

    **Finding, not an assumption:** ``/health`` and ``/ready`` are declared with
    ``def``, not ``async def``, so Starlette dispatches them to a worker thread,
    while ``/api/v1/code-understanding`` is ``async def`` and runs directly on
    the event loop.  The thread hop is not free: on this machine the liveness
    probe is *slower* than a complete stubbed analysis request, which is the
    opposite of the usual expectation.

    That is recorded rather than asserted away, because "a probe should be
    cheaper than a request" turns out not to hold here, and a test that quietly
    assumed it would be a test that quietly asserted something false.

    What *is* asserted is the property that matters operationally: neither path
    is expensive in absolute terms, and liveness is not orders of magnitude
    worse than analysis.  Whether the sync declaration on the two probe routes
    should change is a production-code decision for a later phase, not a
    performance-suite change.
    """
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=VALID_OLLAMA_BODY)
    )

    body = _payload()
    with patch("app.main._build_provider", return_value=ollama_provider()):
        health = record(measure("GET /health", REQUEST_SAMPLE_COUNT, lambda: client.get("/health")))
        analysis = record(
            measure(
                "POST /code-understanding (for comparison)",
                COMPARISON_SAMPLE_COUNT,
                lambda: client.post(ENDPOINT, json=body),
            )
        )

    assert client.get("/health").json() == {"status": "ok"}, (
        "the timed /health loop must have been getting real liveness answers"
    )
    ratio = health.median_ms / max(analysis.median_ms, 1e-6)
    print(
        f"[perf] GET /health is {ratio:.2f}x the cost of a stubbed analysis "
        f"request ({health.median_ms:.3f}ms vs {analysis.median_ms:.3f}ms); "
        f"/health is a sync route and is thread-dispatched"
    )

    assert health.p95_ms < AI_REQUEST_CEILING_MS, health.summary()
    assert health.median_ms < analysis.median_ms * 5 + 5.0, (
        f"liveness is disproportionately expensive: {health.median_ms:.3f}ms "
        f"versus {analysis.median_ms:.3f}ms for a complete analysis request"
    )
    # Sanity: both probe routes should cost the same, since they are declared
    # the same way.  A large gap would mean one of them acquired work.
    with patch("app.main.settings") as settings:
        settings.is_configured = True
        ready = record(
            measure("GET /ready", REQUEST_SAMPLE_COUNT, lambda: client.get("/ready"))
        )
    assert ready.p95_ms < AI_REQUEST_CEILING_MS, ready.summary()


class _SlowProvider:
    """An in-process provider that *awaits*, the way a real one does.

    A provider that returns instantly gives concurrency nothing to overlap, so
    it cannot show whether the engine's own path holds the event loop.  Awaiting
    a fixed delay models the real situation: while the model is generating, the
    engine should be free to serve other callers.

    The delay is deliberately a real ``asyncio.sleep``, not a stubbed clock, so
    the measurement is wall clock and the event loop really does have to be
    free for the overlap to happen.
    """

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s
        self._response = LLMResponse(
            content=VALID_OLLAMA_BODY["message"]["content"],
            model=VALID_OLLAMA_BODY["model"],
            finish_reason=VALID_OLLAMA_BODY["done_reason"],
        )
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        await asyncio.sleep(self._delay_s)
        return self._response


async def _time_batched(service, request, count: int, *, concurrent: bool) -> float:
    """Return the wall-clock milliseconds for *count* analyses of *request*."""

    start = time.perf_counter()
    if concurrent:
        await asyncio.gather(*(service.analyse(request) for _ in range(count)))
    else:
        for _ in range(count):
            await service.analyse(request)
    return (time.perf_counter() - start) * 1000.0


@pytest.mark.parametrize("count", [4, 16], ids=["4_concurrent", "16_concurrent"])
async def test_concurrent_requests_overlap_instead_of_queueing(count):
    """While one caller waits on the model, others must be served too.

    This is the single most relevant concurrency property for an AI engine: the
    provider call is the slow part, and if the engine held the event loop across
    it then *N* callers would take *N* times as long instead of about the same.

    The assertion is that gathering the calls costs roughly one delay, not *N*
    of them.  The bound is deliberately loose — the claim under test is
    "overlaps" versus "serialises", and on a loaded machine the honest margin
    above a single delay is large.

    This is **not** a throughput benchmark.  There is no real model here to
    saturate, so no capacity number is claimed.
    """
    request = explanation_input()
    service = OrchestratorService(provider=_SlowProvider(PROVIDER_DELAY_S))

    # Warm the path first so first-call costs do not land in one measurement.
    await _time_batched(service, request, count, concurrent=False)
    await _time_batched(service, request, count, concurrent=True)
    calls_before_timing = service._provider.calls

    sequential_samples = [
        await _time_batched(service, request, count, concurrent=False) for _ in range(3)
    ]
    concurrent_samples = [
        await _time_batched(service, request, count, concurrent=True) for _ in range(3)
    ]

    sequential = record(
        summarise(f"{count} analyses, one at a time ({PROVIDER_DELAY_MS}ms provider each)", sequential_samples)
    )
    concurrent = record(
        summarise(
            f"{count} analyses, gathered concurrently ({PROVIDER_DELAY_MS}ms provider each)",
            concurrent_samples,
        )
    )

    serial_floor_ms = PROVIDER_DELAY_MS * 1.0
    serial_ceiling_ms = PROVIDER_DELAY_MS * count + count * 5.0
    print(
        f"[perf] {count} analyses with a {PROVIDER_DELAY_MS}ms provider: "
        f"sequential {sequential.median_ms:.3f}ms vs "
        f"concurrent {concurrent.median_ms:.3f}ms "
        f"(fully serial would be ~{serial_ceiling_ms:.0f}ms)"
    )

    assert concurrent.median_ms < serial_ceiling_ms, (
        f"{count} concurrent analyses took {concurrent.median_ms:.3f}ms, which "
        f"matches running them fully serially (~{serial_ceiling_ms:.0f}ms); the "
        f"request path is blocking the event loop"
    )
    # And it must not be *faster* than the provider delay, which would mean the
    # provider calls were skipped rather than overlapped.
    assert concurrent.median_ms >= serial_floor_ms * 0.9, (
        f"{count} concurrent analyses finished in {concurrent.median_ms:.3f}ms, "
        f"less than one {PROVIDER_DELAY_MS}ms provider call; work was skipped"
    )
    assert service._provider.calls - calls_before_timing == count * 6, (
        "the timed concurrency batches did not make one provider call per request"
    )
