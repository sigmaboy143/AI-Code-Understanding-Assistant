# Task 07 — AI Engine → Ollama timeout analysis (IBM Bob)

**Date:** 2026-09-27
**Branch:** `feature/member3-ai-perf-regression-bob`
**Repository:** `E:\AI-Code-Understanding-Assistant-bob` (analysed in place, in IBM Bob)
**IBM Bob:** `1.126.0+bob2.2.0`

> This is the real analysis, carried out against this repository's real source.
> No production code was changed: the fix below is a recommendation only, because
> the Phase 13 blocker is explicitly out of scope for this phase.

---

## 1. The question

Why does a full `POST /api/v1/code-understanding` against the local `qwen3:8b`
model fail to complete inside its request budget?

## 2. The timeout budget, precisely

The production read budget is **60 seconds**, not 120.

- `app/config.py:56-59` — `request_timeout` defaults to `int(os.getenv("REQUEST_TIMEOUT", "60"))`.
- `app/main.py:65-69` — `_build_provider()` passes `timeout=settings.request_timeout`
  straight into `OllamaProvider`.
- `app/providers/ollama.py:40` — `OllamaProvider.__init__` default is also `60`.

The **120 s** figure belongs to the Phase 13 *investigation* budget (and to the
`ollama_provider()` test fixture, which uses `timeout=120`). Both budgets are
discussed below because the conclusion holds for either: the request does not
finish inside 60 s, and it does not finish inside 120 s either.

## 3. Root cause

**`OllamaProvider.complete()` sends no generation cap and no thinking flag, so
with a reasoning model the response length is bounded only by the model's own
stop condition — which for this prompt is longer than the request budget.**

The payload is built at `app/providers/ollama.py:55-63`:

```python
payload = {
    "model": self._model,
    "messages": [
        {"role": m.role, "content": m.content} for m in request.messages
    ],
    "stream": False,
}
if request.temperature is not None:
    payload["options"] = {"temperature": request.temperature}
```

Two things are absent:

- **`num_predict` is never set.** There is no upper bound on generated tokens.
  `options` is only ever populated with `temperature`, and only when the caller
  set one.
- **`think` is never set.** `qwen3:8b` is a reasoning model, so it emits a
  `thinking` trace before `content` by default.

`stream: False` (line 60) is correct and is *not* the cause — it is what makes
the request a single blocking read at all.

## 4. Live evidence

All probes were run out-of-band against the running daemon at
`127.0.0.1:11434`, using tiny synthetic input. Scripts lived in the system temp
directory and are **not** part of this commit.

| # | Probe | Bound | Result |
| --- | --- | --- | --- |
| P1 | Ollama version | — | `0.34.4`, reachable in **0.011 s** |
| P2 | Installed models | — | only `qwen3:8b` (5,225,388,164 bytes, 8.2B, family `qwen3`) |
| P3 | Capped + `think:false` + `num_predict:8`, tiny input | 90 s | **12.025 s**, HTTP 200, `done_reason: stop`, `load_duration` 10.92 s, `prompt_eval_duration` 0.656 s, `eval_count` 2 |
| P4 | Uncapped, tiny input | 30 s | **20.958 s**, HTTP 200, `done`, **`message.thinking` present**, `eval_count` 103, `eval_duration` 10.34 s, `prompt_eval_duration` 10.29 s |
| P5 | **The engine's exact payload, uncapped** | 30 s | **`CLIENT_TIMEOUT` at 30.317 s** (`ReadTimeout`) |
| P6 | Warm, capped, minimal | 60 s | **1.139 s**, HTTP 200, `load_duration` 4.5 ms, `prompt_eval` 620.9 ms, `eval` 103.2 ms, no `thinking` key |
| P7 | **The engine's exact prompt + `think:false` + `num_predict:128`** | 90 s | **15.269 s**, HTTP 200, `done_reason: "stop"`, correct explanation returned, `prompt_eval` 3449.5 ms, `eval` 11392.5 ms, `eval_count` 108, `prompt_eval_count` 213, no `thinking` key |

### What the probes rule out

- **Not a broken or absent daemon.** P1 reaches it in 11 ms; P6 completes a
  warm minimal request in 1.139 s.
- **Not prompt size.** P7 sends the *same* prompt as P5 and returns in 15.269 s.
  The only differences are `think: false` and `num_predict: 128`.
- **Not cold model load.** P3's `load_duration` is 10.92 s, but P6 is warm and
  still shows the same answer in 1.139 s. Load is a one-off cost, not the blocker.
- **Not `stream: False` per se.** Streaming would not shorten generation.

### What the probes confirm

The difference between P5 (times out) and P7 (answers in 15.3 s) is
**unbounded generation on a thinking model**. P4 shows the mechanism directly:
with no cap, the response carries a `thinking` trace and `eval_count` 103 on a
*trivial* input, consuming 10.34 s of evaluation.

This empirically confirms the diagnosis already recorded in the docstring of
`tests/integration/test_failure_states.py`.

## 5. Minimal production fix (recommended, **not applied**)

Add an explicit generation cap and disable thinking to the payload at
`app/providers/ollama.py:55-63`:

```python
payload = {
    "model": self._model,
    "messages": [
        {"role": m.role, "content": m.content} for m in request.messages
    ],
    "stream": False,
    "think": False,
}
options: dict = {}
if request.temperature is not None:
    options["temperature"] = request.temperature
options.setdefault("num_predict", <cap>)
if options:
    payload["options"] = options
```

P7 measured this exact configuration returning a correct explanation in
**15.269 s** — inside both the 60 s production budget and the 120 s
investigation budget, with `done_reason: "stop"` rather than a truncation.

This is a `OllamaProvider` change, which is explicitly **out of scope** for this
phase, so it is recorded rather than made. `think: false` is also worth gating
behind a setting, because suppressing reasoning is a product decision, not only
a latency one.

## 6. Secondary findings (recorded, not changed)

**6.1 — Thinking content is silently discarded.**
`app/providers/ollama.py:94` reads only `data["message"]["content"]`. When the
model does think (P4), `message["thinking"` carries the entire reasoning trace
and is dropped without trace. This is a correctness issue independent of the
timeout, and it is also the reason a "thinking" model looks pathologically slow
in logs while the provider reports only the short final answer.

**6.2 — The read timeout overshoots its budget by a consistent ~0.65 s.**
`app/providers/ollama.py:68` passes a single scalar to `httpx.AsyncClient`, which
applies it to connect, read, write and pool alike. Measured with a real loopback
peer that accepts and then goes silent:

| Configured budget | Observed |
| --- | --- |
| 0.5 s | 1.116 s |
| 1.0 s | 1.655 s |
| 2.0 s | 2.675 s |

The overshoot is **proportional and consistent**, not a defect — the timeout
does bound the wait, and it scales correctly (this is asserted in
`tests/performance/test_timeout_performance.py`). But the effective wait is
`budget + ~0.65 s`, which is worth knowing when the budget is close to a limit.

**6.3 — 504 vs 502 is decided by substring match on English error text.**
`app/main.py:52` defines `_TIMEOUT_KEYWORDS = ("timed out", "timeout")` and
`app/main.py:192` uses it to choose 504 over 502. It works today because
`app/providers/ollama.py:72,76` both embed "timed out" and
`app/providers/ollama.py:80` ("Cannot connect to Ollama at …") does not. It is
however a coupling between HTTP status and human-readable wording; an exception
type or a dedicated error code would be more robust.

**6.4 — Liveness probes are thread-dispatched; the analysis route is not.**
`app/main.py:116` (`/health`) and `app/main.py:122` (`/ready`) are declared with
`def`, so Starlette runs them on a worker thread. `app/main.py:158`
(`code_understanding`) is `async def` and runs on the event loop. Measured on
this machine, `/health` costs **0.80x–1.31x** a complete stubbed analysis
request depending on machine load — i.e. the thread hop costs about as much as
the entire request. Both figures are in
`apps/ai-engine/docs/ai-performance-report.md`. Making the two probes `async def`
would be a one-word change, but it is a production-code change and is out of
scope here.

## 7. Conclusion

The Phase 13 blocker is **unbounded generation on a thinking model**, not prompt
size, not a broken daemon, and not a network problem. It is reproducible in
30 s (P5) instead of 120 s, is fully explained by P4, and is resolved by the
configuration measured in P7 at 15.269 s.

**The blocker remains open.** It is not fixed by this phase and no claim of a
passing live end-to-end run is made anywhere in this commit.
