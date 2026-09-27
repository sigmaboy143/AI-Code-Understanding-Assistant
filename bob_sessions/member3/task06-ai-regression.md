# Task 06 — AI regression (pointer)

**Date:** 2026-09-27
**Branch:** `feature/member3-ai-perf-regression-bob`

## Result

PHASE 36 ran the full AI Engine suite after the PHASE 35 additions:

```
$ python -m pytest apps/ai-engine/tests -q
816 passed, 2 warnings in 50.38s
```

**No regression.** 816 = 782 pre-existing + 34 new performance tests. Zero
failures, zero errors, zero skips.

## Baseline comparison

The baseline was captured **before any change was made**, on the same machine,
at commit `1c73b34`:

| Run | Result |
| --- | --- |
| Baseline, before any edit | **782 passed**, 2 warnings in 2.60s |
| Full suite after the additions | **816 passed**, 2 warnings in 50.38s |
| Difference | +34 passed (the new performance suite), **0 failed** |

The 2 warnings are the pre-existing Starlette/httpx deprecations from
`fastapi/testclient.py` and `starlette/testclient.py`. They are present in the
baseline and unrelated to this work.

## What was not changed

- **No existing test was rewritten or removed.** The 782 baseline tests are the
  same 782 tests, unmodified.
- **No production code was changed.** Nothing under `apps/ai-engine/app/` was
  touched, so no AI-side fix was warranted: the regression run found no failing
  test, and therefore no cause to make one.
- **No timeout value was altered.**

## Scope of the new suite

The 34 added tests live in `apps/ai-engine/tests/performance/`. Their measured
results are documented in
[`apps/ai-engine/docs/ai-performance-report.md`](../../apps/ai-engine/docs/ai-performance-report.md),
and summarised in [`task05-ai-performance.md`](./task05-ai-performance.md).

## Reproduce

```bash
python -m pytest apps/ai-engine/tests -q
```

Note that the run needs no Ollama daemon, no external network, and no
credentials. The performance suite uses only synthetic input and a loopback
listener it creates and tears down itself.
