# AI / Integration Bug Log

Real defects found in the AI Engine (`apps/ai-engine`) and the Ollama integration during the
member 3 work batch on branch `feature/member3-ai-bob-bug` (baseline `1c73b34`).

Every bug below was **reproduced against this branch** and the evidence recorded is observed
output, not inference. No bug in this log has been fixed — all fixes belong to the AI Engine and
provider architecture, which were explicitly out of scope for this batch.

## Summary

| ID | Title | Severity | Status |
|---|---|---|---|
| [AI-BUG-001](AI-BUG-001-qwen3-code-understanding-timeout.md) | Qwen3/Ollama full code-understanding request exceeds the default provider timeout | High | **Open — known blocker** |
| [AI-BUG-002](AI-BUG-002-maxtokens-dropped-unbounded-generation.md) | `LLMRequest.max_tokens` silently dropped, leaving generation unbounded | High | Open |
| [AI-BUG-003](AI-BUG-003-json-array-body-maps-to-500.md) | Malformed JSON provider body maps to `500` instead of `502` | Medium | Open |
| [AI-BUG-004](AI-BUG-004-provider-base-url-credentials-in-logs.md) | Credentials in `PROVIDER_BASE_URL` written to the server log | Low | Open |
| [AI-BUG-005](AI-BUG-005-context-cap-not-enforced.md) | Context builder "hard cap" not enforced; `truncated` under-reports | Medium | Open |

## Correction to the known blocker

The known Phase 13 blocker had been reported as "full code-understanding times out at 60s **and
120s**". Measurement on this branch does not support the 120s part:

| `REQUEST_TIMEOUT` | Attempts | Timeouts | Successes | Success duration range |
|---|---|---|---|---|
| 60s (default) | 3 | **2** | 1 | 59.9s |
| 120s | 4 | **0** | 4 | 84.6s – 115.5s |

The request **does not time out at 120s** — it succeeded on all four attempts. Across the five
successful runs latency ranged from 59.9s to 115.5s (mean ≈ 89.3s). The accurate description is that
the **default 60-second budget is mis-sized for this workload and fails intermittently**, not that
the request cannot complete. The blocker remains **unresolved** either way.

## Causal chain

AI-BUG-001 (the known Phase 13 blocker) is the user-visible symptom. Two independent defects make it
much more likely to occur and much harder to control:

```
AI-BUG-005  context assembled to 160,000 chars despite an 80,000 "hard cap"
     │        → large, unpredictable prompt (≈40k tokens at maximum)
     ▼
AI-BUG-002  max_tokens silently dropped → no generation cap at all
     │        → response latency is unbounded and highly variable
     ▼
AI-BUG-001  completion lands near/over REQUEST_TIMEOUT
     │        → 504 PROVIDER_TIMEOUT
     ▼
            client sees a failure for a request the model can actually answer
```

AI-BUG-003 and AI-BUG-004 are independent of this chain: AI-BUG-003 is an error-mapping/contract
defect, AI-BUG-004 is a log-hygiene defect.

## Verification environment

All evidence was produced on the following, at baseline `1c73b34`:

| Component | Observed |
|---|---|
| Ollama endpoint | `http://127.0.0.1:11434` reachable, `GET /api/tags` → HTTP 200 |
| Model available | `qwen3:8b` (5,225,388,164 bytes) |
| Simple `POST /api/chat` | HTTP 200, `done_reason=stop` |
| AI Engine route | `POST /api/v1/code-understanding` |
| Test suite | `python -m pytest apps/ai-engine/tests -q` → **782 passed, 2 warnings** |

The full suite passing while all five bugs are open is itself a finding: none of these defects are
covered by an assertion that would fail.

This is structural rather than accidental. `.github/workflows/ai-engine.yml:140-149` runs the suite
with `PROVIDER_BASE_URL: http://192.0.2.1:11434` (RFC 5737 TEST-NET-1, permanently unroutable) and
`MODEL: qwen3:8b`, specifically to prove the suite "never depends on weights being present". No
test in this repository performs a live provider call, so no provider latency, payload, or live
error-mapping behaviour is exercised by CI — which is exactly the surface all five bugs live on.

## Not filed as external issues

The GitHub CLI (`gh`) is not installed in this environment, so no GitHub issues were created and no
issue IDs exist. These are local reports only. The repository/team issue workflow is otherwise
unverified, and creating issues would require authentication that is not available here.
