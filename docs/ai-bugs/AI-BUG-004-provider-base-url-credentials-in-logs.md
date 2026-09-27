# AI-BUG-004 — Credentials in `PROVIDER_BASE_URL` are written to the server log

| Field | Value |
|---|---|
| **Status** | Open — not fixed in this branch |
| **Severity** | Low |
| **Component** | `apps/ai-engine/app/providers/ollama.py`, `apps/ai-engine/app/main.py` |
| **Fixed in this branch?** | No — provider logging is out of scope for this batch |

## Title

`OllamaProvider` interpolates the raw `provider_base_url` into `ProviderError` messages, so
userinfo credentials embedded in the URL are emitted verbatim to the application log.

## Problem

`PROVIDER_BASE_URL` is a free-form operator-supplied URL. If it carries userinfo — a form
Ollama and many reverse proxies accept, and which operators use for authenticated gateways — the
credentials are copied straight into the exception message:

```python
# apps/ai-engine/app/providers/ollama.py:78-85
except httpx.ConnectError as exc:
    raise ProviderError(
        f"Cannot connect to Ollama at {self._base_url}", provider="ollama"
    ) from exc
except httpx.RequestError as exc:
    raise ProviderError(
        f"Ollama HTTP request failed: {exc}", provider="ollama"
    ) from exc
```

`self._base_url` is the unredacted configured value. `main.py` then logs that message:

```python
# apps/ai-engine/app/main.py:201
logger.error("Provider error: %s", msg)
```

The client-facing response body is **not** affected — `main.py` returns the fixed string
`"The AI provider returned an error."`, so this is a log-hygiene defect, not a response leak. It
matters because server logs are commonly shipped to aggregation, backup, or CI artefacts with
broader access than the secret store.

## Affected Component

- `apps/ai-engine/app/providers/ollama.py` — `OllamaProvider.complete`, `ConnectError` / `RequestError` branches (lines 78-85).
- `apps/ai-engine/app/main.py` — `logger.error("Provider error: %s", msg)` (line 201).
- `apps/ai-engine/app/config.py` — `provider_base_url` read verbatim from `PROVIDER_BASE_URL` (line 55).

## Reproduction Steps

1. Set `PROVIDER_BASE_URL=http://admin:<password>@ollama.internal:11434`.
2. Trigger a provider connection failure (Ollama stopped or host unreachable).
3. Observe the emitted log line.

## Expected Result

Credentials should be redacted (or the URL omitted) before the value reaches the log, e.g.
`Cannot connect to Ollama at http://***:***@ollama.internal:11434`.

## Actual Result

The full URL including the password is logged:

```
ERROR Provider error: Cannot connect to Ollama at http://admin:sup3rs3cr3t@ollama.internal:11434
```

| Check | Result |
|---|---|
| Credential present in `ProviderError` message | `True` |
| Credential present in emitted log line | `True` |
| Client-facing body | `"The AI provider returned an error."` — generic, safe |

## Evidence

- Source: `apps/ai-engine/app/providers/ollama.py:78-85` — raw `self._base_url` interpolated into the message.
- Source: `apps/ai-engine/app/main.py:201` — message logged verbatim.
- Source: `apps/ai-engine/app/config.py:55` — no validation or redaction of `PROVIDER_BASE_URL`.
- Observed log line reproduced above. The credential shown is a synthetic value created solely for
  this reproduction; no real secret is involved.
- Positive control: the HTTP response body is confirmed generic, so the defect is confined to logs.

## Possible Cause

The provider treats `PROVIDER_BASE_URL` as non-sensitive on the assumption that a local Ollama
endpoint never needs authentication. Nothing in the config layer redacts userinfo, and the
self-hosted case (`PROVIDER_BASE_URL` pointing at a remote or proxied Ollama) is not handled
separately from the default `http://localhost:11434`.

## Current Status

**Open.** Confirmed reproducible. Not fixed here: provider logging changes are out of scope for
this batch. Severity is low because exposure is limited to server-side logs and requires an
operator to place credentials in the URL in the first place.

## Related Tests

- No test asserts that provider error messages are free of URL userinfo.
- `apps/ai-engine/tests/integration/test_provider_error_handling.py` covers the connection-failure
  path but asserts only on message wording, not on redaction.

Full AI Engine suite on this branch: **782 passed, 2 warnings** — the defect does not fail any test.
