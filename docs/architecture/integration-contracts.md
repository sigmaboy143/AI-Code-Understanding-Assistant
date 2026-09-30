# Integration Contracts

Only contracts that exist in code today are documented here. Endpoints that
appear in older planning documents but have no route handler are listed
explicitly as **not available** so they cannot be mistaken for real.

Source of truth for every field below is the backend's own
`apps/api/src/analysis/contracts/` directory and, for the AI Engine side, the
FastAPI schemas in `apps/ai-engine` (synchronised from `feature/member3-ai` at
`04faea5`).

---

# Part 1 — Frontend → NestJS

The intended client is the VS Code extension on `feature/member2-vscode-frontend`
(head `dc4941c`). Its declared request shapes were checked against the backend
and match. Its unmodified `apiService` and analysis adapter have additionally
been exercised **headlessly against a running backend and AI Engine** in a real
runtime, with all 15 assertions passing. The `vscode-test` suite now also runs
in a real Extension Development Host (`npm test` from the repository root), and
covers the request shapes above against a local HTTP server, without a live
Ollama.

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

**Timeout expectation.** A real analysis takes **13.9–27.3s** depending on model
and cache state (19.2s measured for `llama3`, 18.5s cold / 13.9s warm for
`qwen3:8b`). Any client timeout below that risks aborting a request the backend
is still legitimately processing. The backend's own budget is 60s, and the
extension's client timeout is 70s so it clears that budget.

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

Verified against a live request to the AI Engine at `04faea5`:

| Field | Behaviour on the verified runtime |
|---|---|
| `summary` | Populated by the free-text parser |
| `explanation` | `null` |
| `error_explanation` | Present as a top-level key; **not declared** in the backend contract, so it is dropped |
| `structure` | `null` |
| `dependencies` | **Populated** for Python via deterministic `ast` import parsing |
| `improvements` | `[]` |
| `metadata.confidence` | Present as an extra key, normally `null`; not declared in the backend contract and ignored |

### Known contract drift

These mismatches exist between the AI Engine at `04faea5` and what the backend
consumes. They are recorded here rather than silently reconciled.

1. **`dependencies` is populated but never read.** The AI Engine fills it
   deterministically (e.g. `os` and `json` classified as `standard_library`),
   and `AiEngineResponseContract` declares the field, but the adapter does not
   map it into any NestJS response. The capability is invisible through the API.
2. **`error_explanation` is emitted but undeclared.** It appears in the live
   response body, yet `AiEngineResponseContract` has no such property, so it is
   discarded.
3. **`metadata.confidence` is an undeclared extra key.** Harmless at runtime —
   the adapter reads only `metadata.language` — but it means the backend's
   declared `AiEngineMetadata` is narrower than what the engine actually sends.
4. **`confidence` is nullable upstream but dereferenced unconditionally.** The
   AI Engine declares `ResponseConfidence | None`, while the adapter reads
   `.level`, `.evidence`, and `.notes` directly. Safe for every response
   observed, but an explicit `null` would raise an unhandled `TypeError`.

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
NestJS → AiEngineAdapterProvider → FastAPI AI Engine → Ollama → NestJS
```

| Observation | Value |
|---|---|
| HTTP status | `201` |
| Wall time | 19.2s (`llama3`); 18.5s cold / 13.9s warm (`qwen3:8b`) |
| Correlation | Consistent client-side; **not** propagated to the AI Engine — see below |
| Confidence returned | `unknown`, no numeric score |
| Evidence returned | `source_code` |
| Provider | `OllamaProvider`, real HTTP `200` from `host.docker.internal:11434` |

Runtime was against AI Engine `04faea5`, synchronised into `apps/ai-engine`.

### Cross-hop correlation gap

`AiEngineClient` sends only `Content-Type: application/json`
(`apps/api/src/analysis/adapters/ai-engine.client.ts:92`). It does **not** forward
`X-Request-Id`. The AI Engine's middleware at `04faea5` *would* adopt an inbound
`X-Request-Id` if one were sent, but because none is, it mints its own.

Observed for one request:

| Where | Value |
|---|---|
| Client sent | `task9-crosshop-…` |
| Backend response header | `task9-crosshop-…` (matches) |
| Backend response body `requestId` | `task9-crosshop-…` (matches) |
| Backend `ai_engine_interaction` log | `task9-crosshop-…` (matches) |
| AI Engine `request_id` | a different generated value |

The backend-facing contract is satisfied — header, body, and backend logs are all
consistent. Only the AI Engine's own log line cannot be joined to it. This is
recorded as a known limitation and deliberately not patched, because the
established contract does not require it.
