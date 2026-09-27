# AI-BUG-001 — Qwen3/Ollama full code-understanding request exceeds the default provider timeout

| Field | Value |
|---|---|
| **Status** | **Open — known Phase 13 blocker, NOT fixed** |
| **Severity** | High |
| **Component** | `apps/ai-engine/app/providers/ollama.py`, `apps/ai-engine/app/config.py`, `apps/ai-engine/app/main.py` |
| **Fixed in this branch?** | No — provider architecture fix explicitly out of scope for this batch |

## Title

Real code-understanding requests against `qwen3:8b` need 60–116 seconds, but `REQUEST_TIMEOUT`
defaults to 60, so the request fails as `504 PROVIDER_TIMEOUT` roughly two times in three. Raising
the timeout to 120 succeeds consistently. Generation is unbounded (see AI-BUG-002), so latency is
highly variable and the failure is not deterministic.

## Correction to the previously reported symptom

An earlier account of this blocker stated that the request "times out at 60s **and 120s**". Measured
on this branch, that is **not** what happens. Seven real requests were timed:

- At the default 60s timeout, the request **fails most of the time but does not always**.
- At 120s the request **succeeded on every attempt** (4/4) — it does **not** time out at 120s.

The accurate characterisation is that the **default 60-second budget is mis-sized for this
workload**, not that the request is categorically unable to complete. This distinction matters: the
fix is a sizing/control problem, not a hard capability failure. Full data below.

## Affected Component

- `apps/ai-engine/app/config.py:53-56` — `request_timeout` defaults to `60`.
- `apps/ai-engine/app/providers/ollama.py:36-41,68-77` — timeout applied to the `/api/chat` call; `asyncio.TimeoutError` / `httpx.TimeoutException` become `ProviderError("Ollama request timed out after {timeout}s")`.
- `apps/ai-engine/app/main.py:52,192-200` — `_TIMEOUT_KEYWORDS = ("timed out", "timeout")` maps that message to `504 PROVIDER_TIMEOUT`.
- `apps/ai-engine/.env.example:30` — documents `REQUEST_TIMEOUT=60` as the default.
- `apps/ai-engine/README.md:292` — documents `504 PROVIDER_TIMEOUT` as the contract.

## Reproduction Steps

1. Ensure Ollama is running with `qwen3:8b` present.
2. Leave `REQUEST_TIMEOUT` at its default of `60`.
3. `POST /api/v1/code-understanding` with a real repository file
   (`apps/ai-engine/app/providers/ollama.py`, 4,707-character prompt, `explanation` + `dependencies`
   analyses, plus a question).
4. Observe `504 PROVIDER_TIMEOUT`. Repeat — the outcome varies between runs.

Confirm the timeout itself is not the fault by re-running with `REQUEST_TIMEOUT=120`.

## Expected Result

A code-understanding analysis of a single ~4.7k-character source file completes within the
configured provider timeout and returns `200` with a `CodeUnderstandingResponse`.

## Actual Result

At the default 60s budget the request usually times out and returns
`504 PROVIDER_TIMEOUT`; at 120s it always succeeds, but takes 85–116 seconds.

## Evidence

### Ollama and model are healthy

| Check | Observed |
|---|---|
| `GET http://127.0.0.1:11434/api/tags` | **HTTP 200** |
| Model present | **`qwen3:8b`**, 5,225,388,164 bytes |
| Simple `POST /api/chat` ("Reply with the single word: OK") | **HTTP 200 in 30s**, `done=true`, `done_reason=stop`, `eval_count=132` |

The server is reachable, the model is loaded, and short generations complete comfortably. The
failure is specific to the larger, full code-understanding prompt.

### Measured timings of the identical full request

Prompt: 4,707 characters across 2 messages, `temperature: None`, `max_tokens: None`.
All measurements from the real code path
(`CodeUnderstandingRequest` → `build_reasoning_request` → `OllamaProvider.complete`).

| # | `REQUEST_TIMEOUT` | Outcome | Elapsed | Output chars |
|---|---|---|---|---|
| 1 | 60s | `ProviderError` — timed out after 60s | 62.5s | — |
| 2 | 60s | **SUCCESS** `finish_reason=stop` | **59.9s** | 1,102 |
| 3 | 60s | `ProviderError` — timed out after 60s | 60.8s | — |
| 4 | 120s | **SUCCESS** `finish_reason=stop` | 115.5s | 1,617 |
| 5 | 120s | **SUCCESS** `finish_reason=stop` | 84.6s | 1,746 |
| 6 | 120s | **SUCCESS** `finish_reason=stop` | 98.0s | 1,182 |
| 7 | 120s | **SUCCESS** `finish_reason=stop` | 88.7s | 1,138 |

### Summary of the measurements

| Budget | Attempts | Timeouts | Successes | Success duration range |
|---|---|---|---|---|
| 60s (default) | 3 | **2** | 1 | 59.9s |
| 120s | 4 | **0** | 4 | 84.6s – 115.5s |

Across the 5 successful runs, latency ranged from **59.9s to 115.5s** — a **55.6-second spread**,
mean ≈ 89.3s, median 88.7s. Output length (1,102–1,746 chars) does **not** correlate with duration
(1,746 chars completed in 84.6s while 1,617 chars took 115.5s), which points at generation /
reasoning time rather than output size as the driver.

### Error mapping confirmed on the real route

`ProviderError("Ollama request timed out after 60s")` was fed through the real keyword mapping in
`app.main`:

```
RESULT: ProviderError after 62.5s
provider: ollama
message: Ollama request timed out after 60s
maps_to_504: True
http_status: 504
error_code: PROVIDER_TIMEOUT
```

### Not verified: the NestJS 504 leg

The brief also anticipates that "NestJS eventually returns 504". **This could not be verified.**
`apps/api` does not exist on this branch — the only package present is `apps/ai-engine`:

```
> Get-ChildItem apps
Name
----
ai-engine
> Test-Path "apps/api"
False
```

The AI Engine half of the chain is confirmed above. The NestJS propagation is asserted here only as
far as it is documented in the AI Engine error contract, and is **not** claimed as observed.

## Possible Cause

The default `REQUEST_TIMEOUT=60` was sized without reference to the real cost of a
code-understanding prompt against `qwen3:8b`. Three factors compound:

1. **No generation cap.** `LLMRequest.max_tokens` is silently dropped by `OllamaProvider` and never
   set by `build_reasoning_request`, so `options.num_predict` is never sent. Generation length is
   governed only by the model's own stopping behaviour — see
   [AI-BUG-002](AI-BUG-002-maxtokens-dropped-unbounded-generation.md).
2. **Reasoning-model overhead.** `qwen3:8b` is a thinking model and spends a large, variable
   number of tokens on reasoning before producing the answer. That cost is paid inside the same
   60-second budget, and it is the dominant term.
3. **Unreconciled prompt sizing.** The context builder can assemble up to 160,000 characters
   against a documented 80,000-character cap, so prompt size is not bounded where the cap claims —
   see [AI-BUG-005](AI-BUG-005-context-cap-not-enforced.md).

Because there is no cap, the 55.6-second spread in total latency is expected, and a fixed timeout
placed in the middle of that distribution will fail intermittently by construction.

## Current Status

**Open. Unresolved.** Not fixed in this batch — a provider-architecture fix was explicitly out of
scope, and no change to `OllamaProvider`, `reasoning.py`, or the orchestrator was made.

What is established:

- The model, server, and provider plumbing are **working** — a 120s budget succeeds 4/4.
- The default 60s budget is **too small** for this workload.
- The failure is **intermittent**, not deterministic, and is driven by unbounded generation.

Recommended next step (not performed here): honour `max_tokens` by mapping it to Ollama's
`options.num_predict` and set a sensible default in `build_reasoning_request`. That makes latency
predictable and lets `REQUEST_TIMEOUT` be sized deliberately, rather than raised reactively.

## Related Tests

- `apps/ai-engine/tests/integration/test_failure_states.py:244` — `test_provider_timeout_maps_to_gateway_timeout`
- `apps/ai-engine/tests/integration/test_response_contract.py:274,321` — `504` envelope and `asyncio.TimeoutError` mapping
- `apps/ai-engine/tests/test_api.py:214` — `test_provider_timeout_returns_504`
- `apps/ai-engine/tests/fixtures/failing_providers.py:84` — timeout stub

All of these use a **stubbed** provider, so the suite verifies the 502/504 *mapping* but can never
detect that a real request is too slow. `.github/workflows/ai-engine.yml:140-149` deliberately
points the suite at an unroutable provider URL for the same reason.

Full AI Engine suite on this branch: **782 passed, 2 warnings** — the defect does not fail any test.
