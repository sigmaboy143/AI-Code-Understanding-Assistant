# AI-BUG-003 — Malformed JSON provider body maps to 500 instead of 502

| Field | Value |
|---|---|
| **Status** | Open — not fixed in this branch |
| **Severity** | Medium |
| **Component** | `apps/ai-engine/app/providers/ollama.py`, `apps/ai-engine/app/main.py` |
| **Introduced by** | Pre-existing (guard clause present since the provider was written) |
| **Fixed in this branch?** | No — provider-layer fix is out of scope for this batch |

## Title

`OllamaProvider.complete` raises an uncaught `TypeError` for a JSON array / string / number response body, so the HTTP layer returns `500 INTERNAL_ERROR` instead of the documented `502 PROVIDER_ERROR`.

## Problem

`OllamaProvider.complete` guards response parsing with `except (KeyError, ValueError)`:

```python
# apps/ai-engine/app/providers/ollama.py:92-98
try:
    data = resp.json()
    content: str = data["message"]["content"]
except (KeyError, ValueError) as exc:
    raise ProviderError(
        f"Ollama response parse error: {exc}", provider="ollama"
    ) from exc
```

`data["message"]` only raises `KeyError` when `data` is a **dict**. When the provider returns a
body that is valid JSON but not an object, the subscript raises **`TypeError`**, which the guard
clause does not catch.

The escaping `TypeError` is not a `ProviderError` and not an `asyncio.TimeoutError`, so it falls
past both handlers in `apps/ai-engine/app/main.py` to the catch-all `except Exception` and is
reported as an internal server fault.

This contradicts the documented contract. `apps/ai-engine/README.md:293` states:

| HTTP status | `error.code`           | Cause                                                          |
|-------------|------------------------|----------------------------------------------------------------|
| `502`       | `PROVIDER_ERROR`       | Provider returned an error **or a malformed response**         |

A malformed response should therefore be a `502`, not a `500`.

## Affected Component

- `apps/ai-engine/app/providers/ollama.py` — `OllamaProvider.complete`, the `except (KeyError, ValueError)` guard at line 95.
- `apps/ai-engine/app/main.py` — `code_understanding` route error mapping (lines 189-225).

## Reproduction Steps

1. Start the AI Engine.
2. Stub the provider HTTP response to return a JSON array with HTTP 200.
3. `POST /api/v1/code-understanding` with a valid `CodeUnderstandingRequest`.

Provider-level observation (each body stubbed individually):

| Stubbed 200 body            | Exception raised by provider                          |
|-----------------------------|-------------------------------------------------------|
| `{}` (empty object)         | `ProviderError: Ollama response parse error: 'message'` |
| `<html>oops</html>` (non-JSON) | `ProviderError: Ollama response parse error: Expecting value: line 1 column 1 (char 0)` |
| `[1, 2, 3]` (JSON array)    | **`TypeError: list indices must be integers or slices, not str`** |
| `"plain string"` (JSON string) | **`TypeError: string indices must be integers, not 'str'`** |
| `7` (JSON number)           | **`TypeError: 'int' object is not subscriptable`**     |

End-to-end HTTP status through the real FastAPI route:

| Stubbed 200 body            | HTTP status | `error.code`      |
|-----------------------------|-------------|-------------------|
| `{}`                        | `502`       | `PROVIDER_ERROR`  |
| `<html>oops</html>`         | `502`       | `PROVIDER_ERROR`  |
| connection refused          | `502`       | `PROVIDER_ERROR`  |
| `[1, 2, 3]`                 | **`500`**   | **`INTERNAL_ERROR`** |

Only the JSON array case deviates.

## Expected Result

`502 PROVIDER_ERROR` — consistent with the empty-object and non-JSON cases, and with
`README.md:293` ("a malformed response").

## Actual Result

`500 INTERNAL_ERROR`. The failure is additionally logged with a full traceback via
`logger.exception(...)` in the catch-all handler, so an operator sees an internal fault for what is
a malformed upstream response.

## Evidence

- Source: `apps/ai-engine/app/providers/ollama.py:92-98` — `except (KeyError, ValueError)` cannot catch `TypeError`.
- Source: `apps/ai-engine/app/main.py:189-225` — no `TypeError` handler; falls to `except Exception` → 500.
- Contract: `apps/ai-engine/README.md:293` documents malformed responses as `502`.
- Observed: provider-level exception table and end-to-end HTTP table above.
- The gap is already independently recorded in the repository as a known defect, not a new
  observation — `apps/ai-engine/tests/integration/test_provider_error_handling.py:210-229`:

  > Known gap, recorded rather than papered over: `OllamaProvider.complete` guards the parse with
  > `except (KeyError, ValueError)`. Indexing a *list* with `data["message"]` raises `TypeError`,
  > which that clause does not catch, so the failure escapes as a `TypeError` and the HTTP layer
  > maps it to **500 INTERNAL_ERROR** instead of 502 PROVIDER_ERROR.
  >
  > The status-code mapping is a provider-layer fix owned by the architecture phase, not by this
  > test, so it is documented rather than encoded as expected behaviour.

## Possible Cause

The guard clause was written assuming the only failure modes were a missing key (`KeyError`) and
undecodable JSON (`ValueError`). Non-object JSON documents were not considered. A
`isinstance(data, dict)` check, or widening the clause to include `TypeError`, would align the
behaviour with the documented contract.

## Current Status

**Open.** Confirmed reproducible against the current branch. Not fixed here: the fix belongs to
the provider architecture, which is explicitly out of scope for this batch.

The existing test asserts only the safety invariant (no fabricated content) and deliberately
accepts `(ProviderError, TypeError)`, so the suite stays green and does not mask the defect.

## Related Tests

- `apps/ai-engine/tests/integration/test_provider_error_handling.py:210` — `test_json_array_body_raises_provider_error` (documents the gap).
- `apps/ai-engine/tests/integration/test_provider_error_handling.py:201` — `test_non_json_body_raises_provider_error`.
- `apps/ai-engine/tests/integration/test_provider_error_handling.py:232` — `test_empty_object_body_raises_provider_error`.

Full AI Engine suite on this branch: **782 passed, 2 warnings** — the defect does not fail any test.
