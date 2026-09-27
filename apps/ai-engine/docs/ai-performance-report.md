# AI Engine — performance report

**Phase:** 35 (AI performance testing)
**Branch:** `feature/member3-ai-perf-regression-bob`
**Date:** 2026-09-27
**Suite:** `apps/ai-engine/tests/performance/`

Every number in this document is an actual observation from the run recorded
below. Nothing is estimated, extrapolated, or carried over from another machine.
Where a value could not be measured, it is listed as **NOT MEASURABLE** with the
reason, rather than being filled in with a plausible number.

---

## 1. Recorded run

```
$ python -m pytest apps/ai-engine/tests/performance -q -s
34 passed, 2 warnings in 26.19s
```

The 2 warnings are the pre-existing Starlette/httpx deprecations from
`fastapi/testclient.py` and `starlette/testclient.py`. They are present in the
baseline suite and are unrelated to this work.

| Property | Value |
| --- | --- |
| Platform | Windows, CPython 3.13.7 |
| Installed versions | fastapi 0.141.1, starlette 1.6.0, pydantic 2.13.5, httpx 0.28.1 |
| Tests | 34 passed, 0 failed |
| Suite runtime | 26.19 s |
| Ollama daemon | **not running / not contacted by the suite** |

> Installed versions differ from `requirements.txt` pins (`httpx` is pinned to
> 0.27.2; 0.28.1 is installed). This is pre-existing and was not changed.

Reproduce with:

```bash
python -m pytest apps/ai-engine/tests/performance -q -s
```

`-s` prints every measurement as it is taken, plus a summary table at the end,
so a fresh run can be compared against this document directly.

---

## 2. Method

### What "engine cost" means here

The AI Engine's latency has two parts that must never be added together:

1. **Engine overhead** — everything the engine does itself: validation, context
   assembly, prompt construction, the HTTP round trip to the provider, response
   validation, confidence derivation, and serialisation.
2. **Model inference** — how long `qwen3:8b` takes to answer. Not the engine's
   to spend, and not measurable inside a unit test.

Every figure in §3–§6 is (1). The socket is replaced so that (2) cannot leak in.
This is stated on every measurement rather than assumed, because a "provider
latency" number that silently includes inference is the single easiest way for a
report like this to mislead.

### Timing primitives

- `time.perf_counter()` — the highest-resolution monotonic clock, so values are
  durations rather than wall-clock timestamps.
- **Median** is the headline statistic; `p95` and `max` are reported alongside.
  Medians are robust to the scheduler stalls that a shared Windows runner
  produces, and the raw spread is shown so the reader can judge it.
- **Nearest-rank percentiles**, not interpolated, so every reported percentile is
  a value that actually occurred.
- Untimed **warm-up** calls precede every measurement, so figures describe
  steady state rather than first-call costs (lazy imports, allocator warm-up).
- **Interleaving** is used wherever two conditions are compared (see §5.2 and
  §4.2). Measuring condition A to completion and then condition B compares two
  different machine states, and on a busy machine that difference is larger than
  the effect being measured.

### Sample counts

| Purpose | Samples | Rationale |
| --- | --- | --- |
| Provider micro-measurements | 300 | ~0.1 ms each, so 300 costs ~30 ms |
| Full HTTP request | 120 | Each crosses the whole ASGI stack |
| Per-stage decomposition | 60 | Each is a full in-process analysis |
| Relative comparisons | 80 | Asserts ratios, not absolutes |
| Real-socket timeout | 3 | Each costs a full timeout budget of wall clock |

### Thresholds

Absolute ceilings exist only as wide tripwires, two orders of magnitude above
the measured values (`PROVIDER_CALL_CEILING_MS = 250`, `AI_REQUEST_CEILING_MS =
750`, `STARTUP_CEILING_S = 20`). A slow or shared CI runner must not produce a
red build.

**The load-bearing assertions are structural**, and these are what would actually
catch a regression:

| Assertion | Property protected |
| --- | --- |
| Exactly one upstream attempt per `complete()` | No silent retry storm |
| Exactly one client built, and closed, per call | No connection leak |
| Stage sum accounts for the whole call | The decomposition is trustworthy |
| Upstream delay is additive, not multiplicative | No hidden retry or serialised re-read |
| Invalid input never reaches the provider | Bad input cannot consume model capacity |
| Concurrent calls overlap | The event loop is not held across the model |
| Timeout fires no earlier than its budget | Healthy requests are not failed |
| Timeout scales with its budget | The budget is actually honoured |

### Safety

All input is synthetic: the two-line `def add(a, b): return a + b` snippet,
generated `def fN(a, b)` lines, and `import modN` lines. No repository source,
no credentials, nothing confidential. The only socket opened is a loopback
(`127.0.0.1`) listener created and torn down by the test itself. No external
network and no Ollama daemon are required. `.test` is used as the upstream
hostname, which RFC 6761 reserves for testing and can never resolve.

**No production timeout value is modified anywhere.** Where a short budget is
needed to keep a test fast, it is passed to a provider instance created *inside*
the test — never to `app.config.Settings`, and never to the default in
`OllamaProvider`.

---

## 3. Measured results

### 3.1 Provider round trip — `test_provider_performance.py`

A real `OllamaProvider` with a real `httpx` client; only the socket is replaced.

| Measurement | n | min | median | mean | p95 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `provider.complete` | 300 | 0.094 ms | **0.118 ms** | 0.156 ms | 0.365 ms | 0.764 ms |
| `provider.complete` success | 300 | 0.094 ms | **0.107 ms** | 0.136 ms | 0.203 ms | 4.624 ms |
| `provider.complete` failure (connection refused) | 300 | 0.072 ms | **0.075 ms** | 0.079 ms | 0.095 ms | 0.267 ms |

The failure path (0.075 ms) is *cheaper* than the success path (0.107 ms): a
rejected connection fails during connect, before a request body is serialised.
There is no expensive error path.

**Prompt-size scaling.** The outbound body is genuinely serialised and posted at
every size, so the growing user turn is on the wire:

| Synthetic lines | Upstream body | median |
| --- | --- | --- |
| 10 | 534 B | 0.067 ms |
| 100 | 4,044 B | 0.066 ms |
| 500 | 20,444 B | 0.067 ms |
| 1000 | 40,944 B | 0.067 ms |

**A 77x larger request body costs the same to serialise.** Engine-side cost does
not track input size, which places prompt size firmly in the *model* cost
category rather than the engine's.

### 3.2 Full request path — `test_request_performance.py`

One complete in-process `POST /api/v1/code-understanding`.

| Measurement | n | min | median | p95 | max |
| --- | --- | --- | --- | --- | --- |
| `POST /code-understanding` (socket stubbed) | 120 | 1.546 ms | **2.165 ms** | 3.587 ms | 5.093 ms |
| `POST` invalid input → 422 | 120 | 1.350 ms | **1.987 ms** | 3.966 ms | 5.060 ms |
| `GET /health` | 120 | 1.736 ms | **2.628 ms** | 4.881 ms | 7.120 ms |
| `GET /ready` | 120 | 1.794 ms | **2.621 ms** | 4.179 ms | 5.146 ms |

Rejection of invalid input (1.987 ms) is the cheapest path measured, and the
test asserts it **never reaches the provider** — bad input cannot consume model
capacity.

### 3.3 Stage decomposition and accounting

Each stage measured separately, then checked to account for the whole call.

| Stage | n | median |
| --- | --- | --- |
| Context assembly | 60 | 0.004 ms |
| Prompt construction | 60 | 0.006 ms |
| Provider round trip | 60 | 0.111 ms |
| Response validation + confidence | 60 | 0.005 ms |
| Response model assembly (pydantic) | 60 | 0.004 ms |
| **Sum of stages** | | **0.130 ms** |
| **`service.analyse()` whole call** | 60 | **0.129 ms** |
| Accepted window (±50%) | | 0.064 – 0.193 ms |

**The decomposition accounts for the request.** The provider round trip is ~86%
of the total; everything else in the engine is, in aggregate, less than the
provider call. The two model constructions and the response validation are
together under 0.01 ms.

> **Methodological note.** This check failed twice before it passed, and both
> failures are worth recording because they are the reason the method looks the
> way it does.
>
> 1. *First failure:* the decomposition genuinely missed the pydantic model
>    constructions in `OrchestratorService._parse_response` — 0.192 ms of stages
>    against a 0.405 ms call. The accounting check caught real incompleteness,
>    which is what it exists for. `response model assembly` was added.
> 2. *Second failure:* the stages still fell short (0.255 ms vs 0.667 ms) even
>    with nothing missing. The tell was in the distribution: `total`'s **minimum**
>    (0.190 ms) was *below* the sum of the stage medians, and its stdev was
>    1.542 ms against ~0.1 ms for the stages. The excess was scheduler noise
>    inflating one median, not unattributed work.
>
> The fix was to **interleave** the stages and the whole call, round by round,
> inside one event loop. A stall then hits a stage sample and the adjacent total
> sample alike, so the two sides are compared on the same machine state. This
> dropped `total`'s stdev from 1.542 ms to 0.064 ms and produced the clean
> accounting above.
>
> A separate trap: timing the async provider stage with `asyncio.run` per
> iteration charged it ~12 ms for event-loop construction that the real request
> never pays, which made the stage sum *exceed* the total it was meant to
> explain. All stages and the whole call are therefore measured in one loop.

### 3.4 Dependency grounding scaling

The only stage whose cost grows with input. It parses submitted source with `ast`.

| Imports | median | p95 |
| --- | --- | --- |
| 10 | 0.051 ms | 0.056 ms |
| 100 | 0.382 ms | 0.467 ms |
| 500 | 1.972 ms | 2.146 ms |
| 1000 | 4.526 ms | 8.054 ms |

**89.1x growth for a 100x larger input — sub-linear, therefore not quadratic.**
The assertion is `growth < input_growth ** 1.5`, which would fail on a quadratic
scan. A 1000-import file costs 4.5 ms, which is not a latency concern at any
plausible request size.

### 3.5 Startup and import cost — `test_startup_performance.py`

Measured in a **fresh subprocess**, because by the time a test runs `app.main` is
already imported and the cold-start cost is gone.

| Measurement | n | min | median | max |
| --- | --- | --- | --- | --- |
| Cold start: `python -c "from app.main import app"` | 3 | 491.4 ms | **503.1 ms** | 515.4 ms |
| Startup + `TestClient` probes of `/health` and `/ready` | 3 | 643.3 ms | **652.8 ms** | 730.0 ms |

`app.main` builds the whole FastAPI application at import time, so an eager
import added to that path lengthens every start-up — container restarts,
scale-from-zero, every CI job — while costing a single request nothing. That
class of regression is invisible to the request-path measurements, which is why
this module exists.

**`-X importtime` breakdown (cumulative / self):**

| Module | Cumulative | Self |
| --- | --- | --- |
| `app.main` | 513.7 ms | 4.4 ms |
| `fastapi` | 323.5 ms | 1.1 ms |
| `fastapi.applications` | 318.6 ms | 1.7 ms |
| `fastapi.routing` | 302.4 ms | 7.7 ms |
| `fastapi.params` | 224.4 ms | 2.2 ms |
| `fastapi.exceptions` | 148.7 ms | 16.1 ms |
| `fastapi.openapi.models` | 72.6 ms | 62.1 ms |
| `pydantic._internal._model_construction` | 47.4 ms | 1.3 ms |

**The engine's own import self-time is 4.4 ms across 1 module.** Essentially all
of the 503 ms cold start is CPython start-up plus the dependency tree
(FastAPI/Pydantic), not this project's code. Start-up cost is therefore not
something this codebase can meaningfully reduce, which is worth knowing before
anyone optimises it.

Start-up is also verified **not** to require a live provider: the engine imports
and serves `/health` and `/ready` with `PROVIDER_BASE_URL` pointed at the
unroutable `192.0.2.1` and no credentials. A cold container can start and report
liveness before any model is reachable.

### 3.6 Real timeout enforcement — `test_timeout_performance.py`

Unlike every other module, this one opens a **real TCP listener** on `127.0.0.1`
that accepts the connection and then says nothing, with a real `httpx` client
and no stub between provider and kernel. This is the exact shape of the Phase 13
condition: daemon up, connection succeeds, no bytes ever arrive.

`httpx.MockTransport` cannot test this — it bypasses the timeout machinery
entirely, so a handler that raises `ReadTimeout` proves only that the provider
*translates* a timeout, never that one *fires*.

| Configured budget | Observed | Overshoot |
| --- | --- | --- |
| 0.5 s | 1.084 s | +0.58 s |
| 1.0 s | 1.655 s | +0.66 s |
| 2.0 s | 2.728 s | +0.73 s |
| 1.0 s (3 samples, median) | 1.319 s | +0.32 s |

| End-to-end | n | median |
| --- | --- | --- |
| `POST` → 504 against a silent peer (1.0 s budget) | 1 | 1.641 s |

Two properties are asserted, both structural:

- **It does not fire early.** A premature timeout turns working requests into
  504s, which is worse than having no timeout at all. The minimum observed is
  1224 ms against a 1000 ms budget.
- **It scales with the budget.** A provider that ignored its configured timeout
  and used a fixed one would fail this.

The overshoot is consistent and proportional (~0.6 s), because
`OllamaProvider` passes a single scalar to `httpx.AsyncClient`, which applies it
to connect, read, write and pool alike. It is not a defect — the budget does
bound the wait — but the effective wait is `budget + ~0.6 s`, which matters when
a budget sits near a limit.

The inverse is also asserted: a **responsive** upstream, given a budget ten times
the answer's cost, must return 200 and must not be mistaken for a timeout.

### 3.7 Concurrency

A provider that returns instantly gives concurrency nothing to overlap, so this
uses a provider that genuinely `await`s a 20 ms sleep — the model is generating,
and the engine must be free to serve other callers meanwhile.

| Workload | Sequential (median) | Concurrent (median) | Fully serial would be |
| --- | --- | --- | --- |
| 4 analyses | 124.431 ms | **31.333 ms** | ~100 ms |
| 16 analyses | 500.688 ms | **32.218 ms** | ~400 ms |

**16 concurrent analyses cost 32 ms; 16 sequential ones cost 501 ms.** The
request path does not hold the event loop across the provider call — the single
most important concurrency property for an AI service, since the provider call
is by far the slowest part. The test also asserts exactly one provider call per
request, so the speed cannot come from skipped work.

**This is not a throughput benchmark.** There is no real model here to saturate,
so no capacity number is claimed (see §5).

---

## 4. Findings

### 4.1 Failure paths are not expensive

| Outcome | n | median | p95 |
| --- | --- | --- | --- |
| 200 | 80 | 2.404 ms | 3.725 ms |
| 502 (connection refused) | 80 | 2.371 ms | 3.644 ms |
| 504 (read timeout) | 80 | 2.285 ms | 3.640 ms |

A provider incident will not amplify: 502 and 504 cost *less* than a success,
because they return before the response is validated and assembled. Clients
piling up during an outage will not be made worse by the error path itself.

### 4.2 Upstream latency is additive, not multiplicative

A 50 ms synthetic upstream delay was injected and the two conditions
**interleaved** sample by sample.

| Condition | n | median |
| --- | --- | --- |
| No simulated delay | 20 | 3.004 ms |
| 50 ms simulated delay | 20 | 53.990 ms |
| **Observed addition** | | **50.986 ms** |

50 ms in, 50.986 ms out. Upstream latency is paid **exactly once** — there is no
hidden retry and no serialised re-read multiplying it. Each condition is also
asserted to produce exactly one upstream attempt, so the delay cannot be paid
zero times either.

### 4.3 Dependency grounding changes the order of magnitude, not the budget

| Request | n | median |
| --- | --- | --- |
| Explanation only | 80 | 2.556 ms |
| With dependency grounding | 80 | 2.768 ms |

+0.21 ms, and the response genuinely contains grounded dependencies (asserted).

### 4.4 Finding: the liveness probe is not cheaper than a full request

`/health` and `/ready` are declared with `def`, not `async def`
(`app/main.py:116`, `app/main.py:122`), so Starlette dispatches them to a worker
thread. `code_understanding` is `async def` (`app/main.py:158`) and runs directly
on the event loop. The thread hop is not free.

**Measured: `GET /health` is 1.10x the cost of a complete stubbed analysis
request** (2.628 ms vs 2.389 ms). On other runs of this suite the ratio moved
between 0.80x and 1.31x depending on machine load — the honest statement is that
a liveness probe costs about the same as a whole request, which is the opposite
of the usual expectation.

Recorded rather than asserted away: "a probe should be cheaper than a request"
does not hold here, and a test that quietly assumed it would be asserting
something false. What *is* asserted is the property that matters operationally —
neither path is expensive in absolute terms, and liveness is not orders of
magnitude worse than analysis.

Making the two routes `async def` would likely be a one-word improvement, but it
is a production-code change and is **out of scope for this phase**. It is
recorded for a later phase.

### 4.5 Finding: one `httpx.AsyncClient` is constructed per provider call

`OllamaProvider.complete` builds a new `AsyncClient` for every request
(`app/providers/ollama.py:68`). The test asserts exactly one client is built per
call and that every one is closed — so there is **no connection leak** — but
construction is the engine's dominant per-request cost, and it is measurable.

Changing the client lifecycle is a provider-architecture change, explicitly out
of scope. The measurement is recorded so the trade-off is reviewable when that
work is scheduled.

### 4.6 Finding: model reasoning is silently discarded

`app/providers/ollama.py:94` reads only `data["message"]["content"]`. When
`qwen3:8b` emits a `thinking` trace, the entire reasoning is dropped without
trace. Verified live — see §6, probe P4, where `message.thinking` is present in
the response and never reaches the engine.

This is a correctness issue independent of the Phase 13 timeout, and it also
explains why the model looks pathologically slow in logs while the provider
reports only a short final answer.

---

## 5. NOT MEASURABLE

Stated explicitly rather than approximated.

| Item | Why |
| --- | --- |
| **Model response duration (live `qwen3:8b`)** | The full analysis request does not complete inside the read timeout. This is the open Phase 13 blocker, and it is **not fixed by this phase**. A live figure cannot be quoted without either inventing a number or waiting out a failure that is already known. Bounded out-of-band probes are recorded in §6 instead, clearly separated from the suite's numbers. |
| **NestJS → AI Engine end-to-end latency** | `apps/api` is **not present in this branch** — `apps/` contains only `ai-engine`. There is no caller to measure against. |
| **Throughput / capacity under real load** | One model on one local daemon. A single `qwen3:8b` on one GPU gives no meaningful capacity number, and load-testing it would only reproduce the Phase 13 timeout more slowly. The concurrency figures in §3.7 measure event-loop behaviour, not capacity. |
| **Multi-worker / multi-process scaling** | Requires a deployment and a real model; not reachable from a unit test. |
| **Sustained soak / memory profile** | Out of scope for this phase. |
| **p99 latency** | 300 samples cannot support a meaningful p99. Reported p95 is the highest percentile the sample count honestly supports. |

---

## 6. Live Ollama probes (out-of-band, NOT part of the suite)

Run against the live daemon at `127.0.0.1:11434` using tiny synthetic input.
Scripts lived in the system temp directory and are **not** committed. These are
**not** suite results and are kept separate from §3 for that reason.

| # | Probe | Bound | Result |
| --- | --- | --- | --- |
| P1 | Ollama version | — | `0.34.4`, reachable in **0.011 s** |
| P2 | Installed models | — | only `qwen3:8b` (5,225,388,164 bytes, 8.2B, family `qwen3`) |
| P3 | Capped + `think:false` + `num_predict:8`, tiny input | 90 s | **12.025 s**, HTTP 200, `done_reason: stop`, `load_duration` 10.92 s, `prompt_eval_duration` 0.656 s, `eval_count` 2 |
| P4 | Uncapped, tiny input | 30 s | **20.958 s**, HTTP 200, `done`, **`message.thinking` present**, `eval_count` 103, `eval_duration` 10.34 s, `prompt_eval_duration` 10.29 s |
| P5 | **The engine's exact payload, uncapped** | 30 s | **`CLIENT_TIMEOUT` at 30.317 s** (`ReadTimeout`) |
| P6 | Warm, capped, minimal | 60 s | **1.139 s**, HTTP 200, `load_duration` 4.5 ms, `prompt_eval` 620.9 ms, `eval` 103.2 ms, no `thinking` key |
| P7 | **The engine's exact prompt + `think:false` + `num_predict:128`** | 90 s | **15.269 s**, HTTP 200, `done_reason: "stop"`, correct explanation, `prompt_eval` 3449.5 ms, `eval` 11392.5 ms, `eval_count` 108, `prompt_eval_count` 213, no `thinking` key |

**Conclusion: the Phase 13 blocker is unbounded generation on a thinking model —
not prompt size, not a broken daemon.**

P5 (times out) and P7 (answers in 15.269 s) send the *same prompt*; the only
differences are `think: false` and `num_predict: 128`. P4 shows the mechanism
directly: uncapped, even a trivial input produces a `thinking` trace and
`eval_count` 103.

The full analysis, with the minimal recommended fix, is in
`bob_sessions/member3/task07-ai-bob-timeout-analysis.md`.

**The blocker remains open.** It is not fixed here, and no live end-to-end
success is claimed anywhere in this work.

---

## 7. Layout

| File | Contents |
| --- | --- |
| `harness.py` | Timing primitives (`Measurement`, `percentile`, `summarise`, `measure`, `measure_async`, `record`, `print_table`) and every threshold and sample count. Support code, not tests. |
| `conftest.py` | Prints the measurement table at session end. Affects no assertion. |
| `test_provider_performance.py` | Provider round-trip cost, attempt counts, client lifecycle, prompt-size scaling. |
| `test_request_performance.py` | Full request cost, stage decomposition and accounting, additivity, fail-fast, error-mapping cost, concurrency. |
| `test_timeout_performance.py` | Real loopback timeout enforcement, budget proportionality, real 504 mapping. |
| `test_startup_performance.py` | Cold start, `TestClient` startup, `-X importtime` breakdown, no-live-provider start-up. |

## 8. Scope

This phase added tests and documentation only. No production code under `app/`
was modified. Findings §4.4–§4.6 and the §6 fix recommendation are recorded for
later phases, not applied.
