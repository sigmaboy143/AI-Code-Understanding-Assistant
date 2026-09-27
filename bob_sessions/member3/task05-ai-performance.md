# Task 05 — AI performance (pointer)

**Date:** 2026-09-27
**Branch:** `feature/member3-ai-perf-regression-bob`

## Result

PHASE 35 added a dedicated performance suite to the AI Engine:

```
$ python -m pytest apps/ai-engine/tests/performance -q -s
34 passed, 2 warnings in 26.19s
```

**34 tests, 0 failures.** The 2 warnings are the pre-existing Starlette/httpx
deprecations, present in the baseline suite and unrelated to this work.

## Where the work lives

This file is a pointer only. The full report — every measured number, the
method, the thresholds, the findings, and the NOT MEASURABLE table — is in:

**[`apps/ai-engine/docs/ai-performance-report.md`](../../apps/ai-engine/docs/ai-performance-report.md)**

The suite itself is `apps/ai-engine/tests/performance/`:

| File | Contents |
| --- | --- |
| `harness.py` | Timing primitives and every threshold and sample count. |
| `conftest.py` | Prints the measurement table at session end. |
| `test_provider_performance.py` | Provider round-trip cost, attempt counts, client lifecycle, prompt-size scaling. |
| `test_request_performance.py` | Full request cost, stage decomposition and accounting, additivity, fail-fast, error-mapping cost, concurrency. |
| `test_timeout_performance.py` | Real loopback timeout enforcement, budget proportionality, real 504 mapping. |
| `test_startup_performance.py` | Cold start, `TestClient` startup, `-X importtime` breakdown, no-live-provider start-up. |

## Headline measurements

Every figure is the **engine's own cost** — the model socket is stubbed, so
inference time is excluded and cannot leak into a number here.

| Measurement | median | p95 |
| --- | --- | --- |
| `provider.complete` | 0.118 ms | 0.365 ms |
| `POST /code-understanding` | 2.165 ms | 3.587 ms |
| `POST` invalid input → 422 | 1.987 ms | 3.966 ms |
| `GET /health` | 2.628 ms | 4.881 ms |
| Cold start (`from app.main import app`) | 503.1 ms | — |

## Findings

Six findings are recorded in the report. Three are properties the suite asserts
and protects (§4.1 failure paths are not expensive, §4.2 upstream latency is
additive, §4.3 dependency grounding is a small constant). The other three are
production-code observations that were deliberately **not** changed, because
production code is out of scope for this phase:

- A liveness probe (`/health`, 2.628 ms) costs **1.10x** a complete stubbed
  analysis request (2.389 ms), because both probes are declared `def` rather
  than `async def` (`app/main.py:116`, `app/main.py:122`) and are therefore
  thread-dispatched. Making them `async def` is a one-word change, out of scope.
- One `httpx.AsyncClient` is constructed per provider call
  (`app/providers/ollama.py:68`). There is **no connection leak** — a test
  asserts every client is closed — but construction is the dominant per-request
  cost. The client lifecycle is provider architecture, out of scope.
- Model reasoning is silently discarded at `app/providers/ollama.py:94`, which
  reads only `message["content"]`. A correctness issue independent of the
  timeout, confirmed live by probe P4.

## Explicitly not claimed

- **The live `qwen3:8b` full-analysis latency is NOT MEASURABLE.** It does not
  complete inside the read timeout; that is the open Phase 13 blocker, which
  this phase does **not** fix. No live end-to-end success is claimed anywhere.
- **NestJS → AI Engine latency is NOT MEASURABLE** — `apps/api` does not exist
  on this branch; `apps/` contains only `ai-engine`.
- **Throughput/capacity is NOT MEASURABLE** — one model on one local daemon
  gives no meaningful capacity number. The concurrency figures measure
  event-loop behaviour, not capacity.
- **p99 is NOT MEASURABLE** — 300 samples cannot support it. p95 is the highest
  percentile the sample count honestly supports.

The remaining NOT MEASURABLE items are listed with reasons in the report's §5.

## Scope

Tests and documentation only. No file under `apps/ai-engine/app/` was modified.
No production timeout value was altered; short budgets used by the suite are
passed to provider instances created inside the tests, never to
`app.config.Settings` and never to the `OllamaProvider` default.
