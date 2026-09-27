# AI-BUG-005 — `ContextBuilder` "hard size cap" is not enforced on mandatory fields, and `truncated` under-reports

| Field | Value |
|---|---|
| **Status** | Open — not fixed in this branch |
| **Severity** | Medium |
| **Component** | `apps/ai-engine/app/context_builder/builder.py` |
| **Fixed in this branch?** | No — out of scope for this batch |

## Title

`ContextBuilder` documents a hard character cap on assembled context, but mandatory fields are
never truncated, so a maximal request assembles to 2× the cap while `truncated` still reports
`False`.

## Problem

`ContextBuilder` is documented as enforcing a hard limit:

```python
# apps/ai-engine/app/context_builder/builder.py:9-11
3. Deduplicate retrieved chunks so the same content is never included twice.
4. Apply a hard character-level size cap so the context never exceeds the
   configured ``max_chars`` limit.
```

and the constructor repeats the guarantee:

```python
# apps/ai-engine/app/context_builder/builder.py:146-148
max_chars:
    Hard cap on the total number of characters across all assembled
    context sections.
```

The budget is only ever used to decide whether to include **retrieved chunks**:

```python
# apps/ai-engine/app/context_builder/builder.py:192-198
remaining = self._max_chars
remaining -= len(request.source_code)
if request.question:
    remaining -= len(request.question)
if request.context:
    remaining -= len(request.context)
```

The mandatory fields are subtracted from the budget and then passed through unconditionally in
`BuiltContext` (lines 235-244). Nothing clamps them, and `remaining` is allowed to go negative
without being clamped. Since the schema permits up to
`MAX_SOURCE_CODE_LENGTH` (100,000) + `MAX_QUESTION_LENGTH` (10,000) +
`MAX_CONTEXT_LENGTH` (50,000) = 160,000 characters, the assembled context can reach **twice** the
default `MAX_CONTEXT_CHARS` of 80,000.

Compounding this, the `truncated` flag is set **only** when a retrieved chunk is skipped
(line 214). It is never set when the mandatory fields alone exceed the cap, so a caller inspecting
`truncated` is told nothing was dropped even when the assembled context is double the documented
limit.

This matters beyond tidiness: prompt size drives provider latency, and a 160,000-character prompt is
roughly 40,000 tokens. Combined with the unbounded generation in AI-BUG-002, a maximal request is
close to guaranteed to exceed any fixed `REQUEST_TIMEOUT`, which is the mechanism behind
AI-BUG-001.

## Affected Component

- `apps/ai-engine/app/context_builder/builder.py` — `ContextBuilder.build` budget arithmetic (lines 192-198) and `truncated` flag (line 214).
- `apps/ai-engine/app/schemas/code_understanding.py` — the per-field maxima (100,000 / 10,000 / 50,000) whose sum exceeds the builder's cap.

## Reproduction Steps

1. Construct a `CodeUnderstandingRequest` with maximal mandatory fields:
   `source_code` of 100,000 chars, `question` of 10,000 chars, `context` of 50,000 chars.
2. Call `ContextBuilder().build(request)` with the default `max_chars`.
3. Inspect the size of the assembled context and the `truncated` flag.

## Expected Result

Either the assembled context is capped at `MAX_CONTEXT_CHARS` (80,000), or `truncated` is `True`
signalling that content was dropped to satisfy the cap.

## Actual Result

The cap is silently exceeded by 2× and no loss is reported:

```
MAX_CONTEXT_CHARS (documented cap) = 80000
source_code chars = 100000
question    chars = 10000
context     chars = 50000
mandatory total   = 160000
chunk chars       = 0
assembled total   = 160000
EXCEEDS CAP       = True  (by 80000)
truncated flag    = False
```

| Check | Result |
|---|---|
| Documented cap | `80,000` |
| Assembled context (maximal request) | `160,000` |
| Exceeds cap | `True` (by 80,000) |
| `truncated` flag while over cap | `False` — under-reports |

Control — when a retrieved chunk is present it *is* correctly dropped and reported:

```
chunk included    = 0
truncated flag    = True
```

So `truncated` tracks chunk eviction only, not the true assembled size.

## Evidence

- Source: `apps/ai-engine/app/context_builder/builder.py:9-11` and `:146-148` — the hard-cap guarantee.
- Source: `apps/ai-engine/app/context_builder/builder.py:192-198` — budget is decremented, never clamped, never used to truncate mandatory fields.
- Source: `apps/ai-engine/app/context_builder/builder.py:214` — `truncated` set only inside the chunk loop.
- Source: `apps/ai-engine/app/schemas/code_understanding.py:25-28` — field maxima summing to 160,000 > 80,000.
- Observed output above.

## Possible Cause

The cap appears to have been designed for the retrieval/RAG path, where the question is "how much
retrieved context fits in the remaining budget?". The mandatory fields were treated as fixed cost
that always fits, on the assumption that request-level limits (100k/10k/50k) would keep the total
sane. Those two limits are enforced independently and their sum (160,000) was never reconciled
against `MAX_CONTEXT_CHARS` (80,000). `truncated` then inherits the same scope error because it is
only ever assigned in the chunk-inclusion loop.

## Current Status

**Open.** Confirmed reproducible against the current branch. Not fixed here: the context builder
is part of the AI Engine architecture and is out of scope for this batch.

Note this is a latent, size-dependent defect: it does not affect small requests, only ones whose
mandatory fields approach the schema maxima.

## Related Tests

- `apps/ai-engine/tests/test_context_builder.py:304` — `test_context_builder_respects_max_chars_limit`, whose own docstring scopes it to *"Chunks that push total past max_chars are dropped."* The test uses a **5-character** source code, so the mandatory fields never approach the cap and the overflow path is not exercised.
- `apps/ai-engine/tests/test_context_builder.py:321` / `:332` — assert `truncated` purely in terms of chunk eviction, so the under-reporting behaviour is not caught.
- No test asserts that the total assembled context respects `MAX_CONTEXT_CHARS`, and no test exercises maximal mandatory fields (`100,000` / `10,000` / `50,000`) against the cap.

Full AI Engine suite on this branch: **782 passed, 2 warnings** — the defect does not fail any test.
