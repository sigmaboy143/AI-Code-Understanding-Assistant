# AI-BUG-002 — `LLMRequest.max_tokens` is silently dropped, leaving generation unbounded

| Field | Value |
|---|---|
| **Status** | Open — not fixed in this branch |
| **Severity** | High (direct contributor to AI-BUG-001) |
| **Component** | `apps/ai-engine/app/providers/ollama.py`, `apps/ai-engine/app/reasoning.py` |
| **Fixed in this branch?** | No — provider architecture is out of scope for this batch |

## Title

`max_tokens` is declared on the provider-agnostic `LLMRequest` contract but is never read by
`OllamaProvider` and never set by `build_reasoning_request`, so no code path can bound generation
length. Ollama's `options.num_predict` is never sent.

## Problem

`LLMRequest` declares a generation cap as part of the provider-agnostic contract:

```python
# apps/ai-engine/app/providers/base.py:62-67
max_tokens: int | None = Field(
    default=None,
    ge=1,
    description="Maximum number of tokens in the completion.",
)
```

The only concrete provider reads **only** `temperature` and ignores `max_tokens` entirely:

```python
# apps/ai-engine/app/providers/ollama.py:55-64
payload = {
    "model": self._model,
    "messages": [...],
    "stream": False,
}
if request.temperature is not None:
    payload["options"] = {"temperature": request.temperature}
# request.max_tokens is never consulted; options.num_predict is never set.
```

And the reasoning layer never populates it:

```python
# apps/ai-engine/app/reasoning.py:126
return LLMRequest(messages=[system_msg, user_msg])   # temperature and max_tokens both left None
```

Net effect: a caller can set `max_tokens` and it is silently discarded. There is **no** path in the
engine that bounds how long the model may generate. Because generation length is then governed
only by the model's own stopping behaviour, response latency is unbounded and highly variable —
which is the mechanism behind the timeout in AI-BUG-001, and is especially acute for
reasoning/"thinking" models such as `qwen3:8b` that emit long traces before answering.

## Affected Component

- `apps/ai-engine/app/providers/ollama.py` — `OllamaProvider.complete`, payload construction (lines 55-64).
- `apps/ai-engine/app/providers/base.py` — `LLMRequest.max_tokens` declaration (line 62), currently unimplemented by every provider.
- `apps/ai-engine/app/reasoning.py` — `build_reasoning_request` (line 126) never sets a cap.

## Reproduction Steps

1. Construct an `LLMRequest` with `max_tokens=256` and `temperature=0.0`.
2. Call `OllamaProvider.complete` with the provider HTTP transport stubbed to capture the outgoing payload.
3. Inspect the JSON body sent to `/api/chat`.

## Expected Result

The outgoing payload carries the cap, e.g. `options: {"temperature": 0.0, "num_predict": 256}`.

## Actual Result

The outgoing payload omits it entirely:

```json
{
  "model": "qwen3:8b",
  "messages": [{ "role": "user", "content": "hi" }],
  "stream": false,
  "options": { "temperature": 0.0 }
}
```

Observed on the wire:

| Check | Result |
|---|---|
| caller set `max_tokens` | `256` |
| `options` sent | `{'temperature': 0.0}` |
| `options.num_predict` sent | `None` |
| max_tokens honoured | `False` |

The real code-understanding prompt confirms the field is never populated upstream either:
`temperature: None`, `max_tokens: None`.

## Evidence

- Source: `apps/ai-engine/app/providers/base.py:62` — field is part of the public contract.
- Source: `apps/ai-engine/app/providers/ollama.py:55-64` — only `temperature` is read; `max_tokens` is never referenced.
- Source: `apps/ai-engine/app/reasoning.py:126` — `LLMRequest(messages=[...])` sets neither `temperature` nor `max_tokens`.
- Repo-wide search for `max_tokens|num_predict|num_ctx` across `apps/ai-engine` returns only the declaration in `base.py:62`; `num_predict` appears **nowhere** in application code.
- Observed outgoing payload above.
- Prompt introspection: `temperature: None`, `max_tokens: None` for a real request built from a real repository file.

## Possible Cause

The `max_tokens` field was added to the abstract interface to keep the contract provider-agnostic,
but the Ollama provider was never taught to translate it to Ollama's option name (`num_predict`).
Because the field is `Optional[int] = None` and the reasoning layer never sets it, the omission
produces no error anywhere — it is a silent no-op rather than a visible failure, so the gap is
invisible to both the type checker and the test suite.

## Current Status

**Open.** Confirmed reproducible against the current branch. Not fixed here: the fix requires
touching `OllamaProvider` payload construction and the reasoning layer, which are explicitly out of
scope for this batch.

This bug does **not** by itself cause an error; it removes the only available control over
generation length, and is therefore treated as a contributing cause of AI-BUG-001 rather than an
independent incident.

## Related Tests

- `apps/ai-engine/tests/integration/test_provider_error_handling.py:126` asserts `options == {"temperature": 0.0}` — i.e. the existing test **encodes** the absence of any generation cap, so it will need updating when the bug is fixed.
- No test currently asserts that `max_tokens` reaches the provider.

Full AI Engine suite on this branch: **782 passed, 2 warnings** — the defect does not fail any test.
