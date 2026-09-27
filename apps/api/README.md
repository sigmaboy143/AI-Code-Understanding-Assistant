# Backend — `apps/api`

NestJS 12 HTTP API for the AI-Powered Code Understanding & Developer Assistant.

This service is the **only** caller of the AI Engine. Clients never talk to a
model provider directly.

For the whole project see the [root README](../../README.md).

---

## Purpose

Accepts code from a client, delegates analysis to the AI Engine through a
provider abstraction, and returns a structured result carrying a summary,
confidence metadata, and evidence.

Two things this service is deliberate about:

- **It never invents analysis data.** If the AI Engine reports `UNKNOWN`
  confidence, this service returns `unknown` and omits the numeric score. If it
  returns no symbols, the response carries `symbols: []`.
- **It never leaks internals.** Upstream error messages, the AI Engine URL, and
  stack traces are never forwarded to callers, and source code cannot reach a log
  line.

---

## Setup

Requires **Node 22** (verified on 22.23.2).

```bash
cd apps/api
npm ci
```

`npm ci` is preferred over `npm install`; the type-aware linter resolves
platform binaries through optional dependencies that a partial install can miss.

---

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | Port the server binds |
| `AI_ENGINE_BASE_URL` | `http://127.0.0.1:8000` | Where the AI Engine listens. Bare origin, no trailing slash |
| `AI_ENGINE_TIMEOUT_MS` | `60000` | Milliseconds to wait for one AI Engine call |

```bash
export PORT=3000
export AI_ENGINE_BASE_URL=http://127.0.0.1:8000
export AI_ENGINE_TIMEOUT_MS=60000
```

Read once at module initialisation, so changes need a restart.

**Why 60000:** a real `llama3` analysis was measured at 34.3 seconds. The
previous 10-second default could not have completed against a live model. 60000
also matches the AI Engine's own 60-second provider budget, so it is an upper
bound on the round trip rather than an arbitrary number.

The value is not validated. A non-numeric value becomes `NaN`, which
`setTimeout` treats as "fire immediately" — producing instant timeouts with no
warning.

---

## Run

```bash
npm run start:dev      # watch mode
npm run start          # single run
npm run build          # compile to dist/
npm run start:prod     # run the compiled build
```

---

## Test

```bash
npm run lint           # oxlint --type-aware, 0 warnings/errors expected
npm test               # 19 suites, 455 tests
npm run test:e2e       # 1 suite, 5 tests
npm run build          # tsc
```

All four pass with **no external service running** — no AI Engine, no Ollama, no
database.

> **Always use the npm scripts.** This project compiles TypeScript as ESM and
> the scripts carry `--experimental-vm-modules`. Running `npx jest` directly
> fails on NestJS's ESM-only packages before any test executes. See
> [troubleshooting](../../docs/development/troubleshooting.md).

`npm run test:e2e` uses its own config, `test/jest-e2e.json`, which must stay
aligned with the ESM settings in `jest.config.ts`.

---

## Endpoints

### Operational

| Method | Path | Response |
|---|---|---|
| `GET` | `/health` | `200 {"status":"ok"}`. No network I/O — never fails because of a dependency |
| `GET` | `/ready` | `200 {"status":"ready","aiEngine":"ok"}`, or `503 {"status":"not_ready","aiEngine":"unavailable"}` |

### AI-backed

These call the AI Engine and take roughly 34 seconds with a local `llama3`.

| Method | Path | Status |
|---|---|---|
| `POST` | `/analysis/code` | Implemented |
| `POST` | `/analysis/file` | Implemented |
| `POST` | `/explanations` | Implemented |

**`POST /analysis/code`**

| Field | Required | Validation |
|---|---|---|
| `language` | yes | string |
| `code` | yes | string, max 100000 characters |
| `filePath` | no | string, no length limit |
| `context` | no | string, no length limit |

**`POST /analysis/file`** — identical, except `filePath` is required.

**`POST /explanations`** — accepts `language`, `code`, `filePath`, `startLine`,
`endLine`, `detailLevel`. These fields carry `@Allow()`, which preserves them
through the whitelist but applies **no validation**. `startLine`, `endLine`, and
`detailLevel` are currently accepted and discarded.

### Present but not functional

| Method | Path | Actual behaviour |
|---|---|---|
| `GET` | `/files/:id/analysis` | Hardcoded stub. `summary` undefined, confidence `low`/`model: "none"`. No analysis performed |
| `GET` | `/symbols?filePath=&language=` | Always `[]` |
| `GET` | `/relationships?filePath=&language=` | Always `[]` |

`GET /` returns the NestJS scaffold string `"Hello World!"`. Leftover, not a
feature.

### Not available

`auth`, `users`, `organizations`, `projects`, `repositories`, `conversations`,
`documentation`, `tests`, and `onboarding` declare controllers with **zero
route handlers**. They return `404`; no code serves them.

Full contract detail, including error mapping and correlation-ID rules, is in
[integration-contracts.md](../../docs/architecture/integration-contracts.md).

---

## Response shape

```jsonc
{
  "requestId": "…",          // the X-Request-Id correlation ID
  "language": "typescript",
  "summary": "…",
  "symbols": [],             // always empty today
  "relationships": [],       // always empty today
  "confidence": {
    "level": "confirmed",    // confirmed | inferred | unknown | low | medium | high
    "score": undefined,      // omitted — the AI Engine has no numeric score
    "model": "…",
    "reasoning": "…"
  },
  "evidence": [
    {
      "kind": "source_code",
      "detail": "…",
      "sourceType": "source_code",  // AI Engine source_type, verbatim
      "filePath": "…",
      "lineStart": 1,
      "lineEnd": 10,
      "chunkId": null
    }
  ],
  "analysedAt": "2026-01-01T00:00:00.000Z"
}
```

The AI Engine's `CONFIRMED` / `INFERRED` / `UNKNOWN` are preserved as
`confirmed` / `inferred` / `unknown`. They are deliberately **not** collapsed
into `high` / `medium` / `low`, which would claim a strength the AI Engine never
asserted.

---

## Errors

| Status | Cause |
|---|---|
| `400` | Validation failed, or the AI Engine returned `422 VALIDATION_ERROR` |
| `502` | AI Engine `502 PROVIDER_ERROR` |
| `503` | AI Engine `503 PROVIDER_UNAVAILABLE`, or a network failure |
| `504` | AI Engine `504 PROVIDER_TIMEOUT`, or the local budget elapsed |
| `500` | AI Engine `500 INTERNAL_ERROR`, or an unmapped upstream failure |

Messages are fixed strings written by this service. Upstream text, URLs, and
ports are never included.

---

## Correlation IDs

Every response carries `X-Request-Id`. A caller-supplied ID is honoured if it
matches `/^[A-Za-z0-9._~-]{1,128}$/`; otherwise it is replaced with a fresh
UUID. The same value appears in the header, the response body, and the logs.

CR and LF are rejected deliberately, which blocks header injection and log-line
forging.

---

## Security

**In place**

- Logging is **allowlist-based**. Exactly seven field names are ever read from a
  log call — `operation`, `path`, `status`, `durationMs`, `code`, `requestId`,
  `outcome`. Anything else is dropped rather than filtered, so source code,
  request bodies, response bodies, and URL credentials cannot reach a log line.
  Covered by roughly 60 tests.
- No credentials are read, stored, or logged by this service.
- Validation rejects unknown request properties instead of silently dropping
  them.

**Current limitations — not features**

- **No authentication.** Every endpoint is anonymous.
- **No authorization.** No guards.
- **No rate limiting.** `/analysis/code` is an unmetered path to an LLM. This is
  the most exposed gap.
- **No security headers.** `helmet` is not installed.
- **No CORS configuration.** Safe only because the intended client is an
  extension host rather than a browser.
- `context` and `filePath` have no maximum length.
- `AI_ENGINE_TIMEOUT_MS` is not validated.
- `npm audit` reports 5 advisories, all inside `@nestjs/mau` — a devDependency
  used only by the deploy CLI. `npm audit --omit=dev` reports **0**.

---

## Project layout

```
src/
├── main.ts                  bootstrap; PORT, default 3000
├── app.module.ts            root module; APP_PIPE registered here
├── common/                  correlation, logging, validation — no business logic
├── analysis/                the implemented feature area
│   ├── analysis.service.ts  provider-agnostic; no AI specifics
│   ├── adapters/            the only AI-aware code
│   ├── contracts/           frozen FastAPI request/response types
│   └── models/              AnalysisResult, CodeSymbol, CodeRelationship
├── explanations/            POST /explanations
├── health/                  GET /health, GET /ready
└── files/ symbols/ relationships/ auth/ users/ …   skeletons
```

`AnalysisService` depends on the `ANALYSIS_PROVIDER` token, not on a concrete
client. `AiEngineAdapterProvider` is the only implementation and the only place
the FastAPI contract appears. Replacing the AI Engine means writing one class and
changing one module registration.

---

## Documentation

| Document | Contents |
|---|---|
| [Root README](../../README.md) | Whole project |
| [System Architecture](../../docs/architecture/system-architecture.md) | Layer design and status |
| [Integration Contracts](../../docs/architecture/integration-contracts.md) | Request/response contracts |
| [Environment](../../docs/development/environment.md) | Variables and versions |
| [Testing Guide](../../docs/testing/testing-guide.md) | Commands and determinism |
| [Deployment Guide](../../docs/deployment/deployment-guide.md) | Current startup, what is missing |
| [Troubleshooting](../../docs/development/troubleshooting.md) | Known problems and fixes |
