# Integration Contracts

Only contracts that exist in code today are documented here. Endpoints that
appear in older planning documents but have no route handler are listed
explicitly as **not available** so they cannot be mistaken for real.

Source of truth for every field below is the backend's own
`apps/api/src/analysis/contracts/` directory and, for the AI Engine side, the
FastAPI schemas on `feature/member3-ai` (head `3ee7824`).

---

# Part 1 — Frontend → NestJS

The intended client is the VS Code extension on `feature/member2-vscode-frontend`.
Its declared request shapes were checked against the backend and match. **No
request below has been executed by the extension against a running backend**, so
this part is contract-verified but not runtime-verified.

## 1.1 Common behaviour

**Correlation.** Every response carries an `X-Request-Id` header. If the request
supplied a valid one, it is echoed; otherwise a fresh UUID is generated and used
downstream. Valid means 1–128 characters matching `/^[A-Za-z0-9._~-]{1,128}$/`.
An invalid value is **replaced, not truncated**, and the replacement is what
appears in the header, in the response body, and in logs.

**Content type.** `application/json`.

**Validation.** One global `ValidationPipe` with `whitelist: true` and
`forbidNonWhitelisted: true`. A property with no validation decorator is
stripped; a property the DTO does not declare is rejected with `400`. Because of
`forbidNonWhitelisted`, clients must send exactly the declared fields and no
others.

**Timeout expectation.** A real `llama3` analysis took **34.3s**. Any client
timeout below that will abort a request the backend is still legitimately
processing. The backend's own budget is 60s.

## 1.2 `POST /analysis/code`

Analyses a code string. Calls the AI Engine.

**Request**

| Field | Type | Required | Validation |
|---|---|---|---|
| `language` | string | yes | `@IsString()` |
| `code` | string | yes | `@IsString()`, max 100000 characters |
| `filePath` | string | no | `@IsOptional() @IsString()` — **no length limit** |
| `context` | string | no | `@IsOptional() @IsString()` — **no length limit** |

**Response `200`** — `AnalysisResult`:

| Field | Type | Notes |
|---|---|---|
| `requestId` | string | The correlation ID |
| `language` | string | Echoed |
| `summary` | string \| undefined | From the AI Engine |
| `symbols` | `CodeSymbol[]` | **Always `[]`** — extraction not implemented |
| `relationships` | `CodeRelationship[]` | **Always `[]`** — resolution not implemented |
| `confidence` | object | See below |
| `evidence` | `Evidence[]` | See below |
| `analysedAt` | string | ISO 8601 timestamp |

`confidence`:

| Field | Type | Notes |
|---|---|---|
| `level` | string | `confirmed` \| `inferred` \| `unknown` \| `low` \| `medium` \| `high` |
| `score` | number \| undefined | **Omitted.** The AI Engine has no numeric score |
| `model` | string \| undefined | |
| `reasoning` | string \| undefined | |

`evidence[]` items:

| Field | Type | Notes |
|---|---|---|
| `kind` | string | `syntax` \| `semantic` \| `ai` \| `source_code` \| `retrieved_chunk` \| `file` \| `documentation` \| `test` \| `git_commit` |
| `detail` | string | Human-readable summary |
| `sourceType` | string \| undefined | The AI Engine's `source_type`, verbatim |
| `filePath` | string \| undefined | |
| `lineStart` / `lineEnd` | number \| undefined | |
| `chunkId` | string \| undefined | |

`test` and `git_commit` are reserved by the AI Engine and are never
auto-populated.

**Errors**

| Status | Cause |
|---|---|
| `400` | Validation failed, or the AI Engine returned `422 VALIDATION_ERROR` |
| `502` | AI Engine returned `502 PROVIDER_ERROR` |
| `503` | AI Engine returned `503 PROVIDER_UNAVAILABLE`, or the network call failed |
| `504` | AI Engine returned `504 PROVIDER_TIMEOUT`, or the local 60s budget elapsed |
| `500` | AI Engine returned `500 INTERNAL_ERROR`, or an unmapped upstream failure |

No upstream error text, provider URL, or stack trace is ever included.

## 1.3 `POST /analysis/file`

Identical to `POST /analysis/code` except that `filePath` is **required**
(`@IsNotEmpty()`) and `code` is still supplied in the body. Delegates to the same
provider method and returns the same `AnalysisResult`.

## 1.4 `POST /explanations`

**Request** — `ExplainCodeDto`. Note: every field is decorated `@Allow()`, which
**preserves the field through `whitelist: true` but performs no validation**.
This endpoint therefore accepts any payload; rejection happens downstream at the
AI Engine.

| Field | Type | Actually used? |
|---|---|---|
| `language` | string | yes |
| `code` | string | yes |
| `filePath` | string \| undefined | yes |
| `startLine` | number \| undefined | **no** — accepted and discarded |
| `endLine` | number \| undefined | **no** — accepted and discarded |
| `detailLevel` | `brief` \| `standard` \| `detailed` \| undefined | **no** — accepted and discarded |

**Response `200`**:

| Field | Type | Notes |
|---|---|---|
| `requestId` | string | |
| `summary` | string | Falls back to `"No summary available."` if the AI Engine gave none |
| `detailed` | string \| undefined | **Always `undefined`** today |
| `confidence` | object | Same shape as above |
| `referencedSymbols` | `CodeSymbol[]` | **Always `[]`** — sourced from the result's empty `symbols` |
| `generatedAt` | string | ISO 8601, from `analysedAt` |

This route calls the AI Engine.

## 1.5 `GET /files/:id/analysis`

**STUB.** Returns `200` with hardcoded data. It does not analyse anything.

```jsonc
{
  "requestId": "<the :id value, echoed>",
  "language": "unknown",
  "symbols": [],
  "relationships": [],
  "summary": null,                          // undefined, serialised as absent
  "confidence": {
    "score": 0,
    "level": "low",
    "model": "none",
    "reasoning": "File analysis not yet implemented."
  },
  "evidence": [
    { "kind": "semantic", "detail": "File analysis is a stub. No analysis provider has processed this file." }
  ],
  "analysedAt": "<current ISO 8601>"
}
```

No AI Engine call. Clients must not treat this as analysis output.

## 1.6 `GET /symbols` and `GET /relationships`

Both take the same query parameters:

| Parameter | Required | Notes |
|---|---|---|
| `filePath` | yes | |
| `language` | yes | |

Both return `200` with `[]`. The parameters are accepted and ignored. Neither
calls the AI Engine.

## 1.7 `GET /health` and `GET /ready`

| Route | Response |
|---|---|
| `GET /health` | `200 {"status":"ok"}` — no I/O, never fails because of a dependency |
| `GET /ready` | `200 {"status":"ready","aiEngine":"ok"}` or `503 {"status":"not_ready","aiEngine":"unavailable"}` |

Neither leaks a URL, port, or upstream message.

## 1.8 Not available

These modules declare controllers with **zero route handlers**. Any request
returns `404`:

`/auth`, `/users`, `/organizations`, `/projects`, `/repositories`,
`/conversations`, `/documentation`, `/tests`, `/onboarding`

There is also no route for impact analysis, debugging, architecture, or Git
reasoning. Those exist on the AI Engine side only.

---

# Part 2 — NestJS → AI Engine

Verified in real runtime against `feature/member3-ai`.

## 2.1 Connection

| Setting | Value |
|---|---|
| Base URL | `AI_ENGINE_BASE_URL`, default `http://127.0.0.1:8000` |
| Path | `POST /api/v1/code-understanding` |
| Method | `POST` |
| Content type | `application/json` |
| Auth | None |
| Timeout | `AI_ENGINE_TIMEOUT_MS`, default `60000` |

## 2.2 Request

```jsonc
{
  "source_code": "…",     // required, non-blank, max 100000 chars
  "language": "typescript",
  "file_path": "src/a.ts", // or null
  "question": null,        // always null; not yet in the backend's model
  "context": null,         // or the caller's context
  "analyses": [ … ]        // OMITTED by the backend
}
```

**`analyses` is deliberately omitted.** The AI Engine's schema sets
`min_length=1` and defaults to all five types, so an empty array would be
rejected. Because `JSON.stringify` drops `undefined`, omitting the key makes the
AI Engine apply its own default — the correct behaviour when the caller has no
explicit selection.

Valid `analyses` values, if ever sent explicitly: `explanation`,
`error_explanation`, `structure`, `dependencies`, `improvements`.

## 2.3 Response

```jsonc
{
  "summary": "…",
  "metadata": { "language": "…", "file_path": "…", "analyses": [ … ] },
  "confidence": {
    "level": "CONFIRMED",              // CONFIRMED | INFERRED | UNKNOWN
    "evidence": [
      {
        "source_type": "source_code",  // see 2.5
        "file_path": "…",              // or null
        "line_start": 1,               // or null
        "line_end": 10,                // or null
        "chunk_id": null,              // or null
        "description": "…"             // or null
      }
    ],
    "notes": null
  },
  "explanation": null,
  "structure": null,
  "dependencies": null,
  "improvements": null
}
```

There is **no numeric confidence field** in this contract. `UNKNOWN` means
"insufficient evidence to determine", not "score 0".

## 2.4 Confidence mapping

| AI Engine | Backend `confidence.level` | Numeric `score` |
|---|---|---|
| `CONFIRMED` | `confirmed` | omitted |
| `INFERRED` | `inferred` | omitted |
| `UNKNOWN` | `unknown` | omitted |
| `HIGH` (legacy) | `high` | omitted |
| `MEDIUM` (legacy) | `medium` | omitted |
| `LOW` (legacy) | `low` | omitted |
| anything else | `unknown` | omitted |

The three AI Engine states are **not** collapsed into the older
low/medium/high scale. Doing so would claim a strength the engine never
asserted.

## 2.5 Evidence source types

| `source_type` | Meaning |
|---|---|
| `source_code` | The submitted source itself |
| `retrieved_chunk` | A chunk returned by retrieval |
| `file` | A file on disk |
| `documentation` | Documentation text |
| `test` | Reserved. Never auto-populated |
| `git_commit` | Reserved. Never auto-populated |

These are carried into the backend's `Evidence.sourceType` **verbatim**. The
backend does not reinterpret `source_code` as `syntax` or `documentation` as
`semantic`; that mapping would be a guess.

## 2.6 Analyses behaviour, as observed

| Field | Behaviour on the verified runtime |
|---|---|
| `summary` | Populated by the free-text parser |
| `explanation` | `null` |
| `structure` | `null` |
| `dependencies` | `null` on `532f035`; populated from `3ee7824` onward for Python via deterministic `ast` import parsing |
| `improvements` | `[]` |

### Known contract drift

Two mismatches exist between the AI Engine's current head and what the backend
consumes. Both are recorded here rather than silently reconciled.

1. **`dependencies`** is populated by `3ee7824` but the backend's
   `AiEngineResponseContract` declares the field and never reads it. The
   capability is invisible through the NestJS API.
2. **`error_explanation`** is emitted by the AI Engine's schema but is absent
   from the backend's response contract, so it is dropped.

Additionally, the AI Engine's `confidence` field is declared nullable
(`ResponseConfidence | None`) while the adapter dereferences `.level`
unconditionally. That is safe for every response observed so far, but an
explicit `null` would raise an unhandled `TypeError`.

The AI Engine contract is frozen by team agreement. These are reported for
Member 3 to address in a published contract revision, not for unilateral
adaptation.

## 2.7 Error envelope

Every non-2xx AI Engine response uses one shape:

```jsonc
{ "error": { "code": "VALIDATION_ERROR", "message": "…" } }
```

| AI Engine status | `error.code` | Backend response |
|---|---|---|
| `422` | `VALIDATION_ERROR` | `400 Bad Request` |
| `503` | `PROVIDER_UNAVAILABLE` | `503 Service Unavailable` |
| `504` | `PROVIDER_TIMEOUT` | `504 Gateway Timeout` |
| `502` | `PROVIDER_ERROR` | `502 Bad Gateway` |
| `500` | `INTERNAL_ERROR` | `500 Internal Server Error` |
| network failure | — | `503 Service Unavailable` |
| local budget elapsed | — | `504 Gateway Timeout` |

The backend substitutes its own fixed messages. Upstream `message` text, the AI
Engine URL, port, and stack traces are never forwarded to API callers.

## 2.8 AI Engine health and readiness

| Route | Response | Semantics |
|---|---|---|
| `GET /health` | `200 {"status":"ok"}` | Process is alive. Always 200 while running |
| `GET /ready` | `200` when configured, `503` otherwise | **Configuration only.** Verifies a provider name is set and, for cloud providers, that an API key exists. Makes **no** LLM call |

The backend's `GET /ready` proxies this. It reports `200 {"status":"ready"}` when
the AI Engine's `/ready` succeeds.

**Known consequence:** because the AI Engine's readiness check never touches the
provider, the backend reports ready even when Ollama is down and analysis
requests will fail. Liveness and readiness are both correct; the gap is that
readiness does not test the thing that actually matters.

## 2.9 Verified end-to-end result

```
NestJS → AiEngineAdapterProvider → FastAPI AI Engine → Ollama/llama3 → NestJS
```

| Observation | Value |
|---|---|
| HTTP status | `201` |
| Wall time | ~34.3s |
| Correlation | Matching request IDs on both sides |
| Confidence returned | `unknown` |
| Evidence returned | `source_code` |

Runtime was against AI Engine commit `532f035`. The current AI Engine head is
`3ee7824`; see 2.6 for what changed since.
