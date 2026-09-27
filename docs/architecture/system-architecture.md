# System Architecture

Status of every layer as it exists today. Statements are separated into
**IMPLEMENTED**, **PARTIAL**, and **PLANNED** so that nothing here can be
mistaken for a finished feature.

---

## 1. Request path

```
Developer
   ↓
VS Code Extension / React Webview          IMPLEMENTED (separate branch, not merged)
   ↓  HTTP, X-Request-Id correlation
NestJS Backend  (apps/api)                 IMPLEMENTED
   ↓
   AnalysisService                           IMPLEMENTED
   ↓  ANALYSIS_PROVIDER injection token
   AiEngineAdapterProvider                   IMPLEMENTED
   ↓
   AiEngineClient  (native fetch)           IMPLEMENTED
   ↓  HTTP POST /api/v1/code-understanding
AI Engine  (FastAPI, port 8000)            IMPLEMENTED (apps/ai-engine, in this checkout)
   ↓
   OrchestratorService                       IMPLEMENTED
   ↓
   ContextBuilder + LLM provider             IMPLEMENTED
   ↓
Ollama / LLM  (port 11434)                 EXTERNAL (host process)
   ↓  structured CodeUnderstandingResponse
   Structured result → NestJS AnalysisResult
   ↓  HTTP
VS Code extension renders summary,
confidence and evidence
```

---

## 2. Layer status

### 2.1 VS Code Extension / React Webview — IMPLEMENTED (separate branch)

Not present in this checkout. Developed on `feature/member2-vscode-frontend`
(head `dc4941c`), where the extension's `package.json` sits at the **repository
root** alongside `src/` and `webview-ui/`.

From inspection of that branch: 11 contributed commands, an activity-bar webview,
a React 18 + Zustand + Vite UI, and an axios HTTP client whose request shapes
match the backend. Its `aicode.useMockData` setting defaults to `true`, and its
axios timeout is **70 000 ms**, deliberately larger than the backend's 60s budget
so a slow but successful analysis is not misreported as a client-side timeout.

Verified headlessly against a running backend and AI Engine: lint, `tsc`
compile, webview build, 42 unit tests, and a live client test with 15/15
assertions passing. The full `vscode-test` GUI suite was not executed, because
it downloads and launches VS Code.

### 2.2 NestJS Backend — IMPLEMENTED

`apps/api`, NestJS 12, TypeScript compiled as ESM, Express adapter, port 3000.

Real, working capabilities:

- Global `ValidationPipe` registered as a single `APP_PIPE` provider, with
  `whitelist: true` and `forbidNonWhitelisted: true`.
- Correlation middleware applied to every route via `CommonModule.configure()`,
  which validates and echoes `X-Request-Id`.
- Allowlist-based structured logging that cannot emit source code, request
  bodies, response bodies, or upstream error text.
- Four AI-backed analysis routes plus two operational routes.

### 2.3 Provider abstraction — IMPLEMENTED

`AnalysisService` depends on the `ANALYSIS_PROVIDER` injection token, not on a
concrete AI client. `AiEngineAdapterProvider` is the only implementation, and it
is the only layer that knows the FastAPI contract exists.

`AnalysisService` and `AnalysisController` contain no AI Engine specifics. This
separation is what allows the provider to be replaced without touching
application logic.

### 2.4 AiEngineClient — IMPLEMENTED

Uses native `fetch`. No Axios on the backend. Responsibilities are deliberately
narrow: build the URL, set `Content-Type: application/json`, serialise the exact
contract, abort on a timer, and translate transport failure into a typed
`AiEngineClientError`.

### 2.5 AI Engine — IMPLEMENTED (in this checkout)

`apps/ai-engine`, synchronised from `feature/member3-ai` at `04faea5`, FastAPI on
port 8000. It is part of this checkout and runs alongside the backend. Its
internals: a provider abstraction, a context builder, an orchestrator, several
analysis agents, an output validator, an in-memory retrieval implementation, an
evidence model, and a request-correlation logging context.

`dependencies` is grounded deterministically by parsing Python `import`
statements with `ast`, never by reading dependency names out of model output.
Its Ollama provider sends a generation cap (`num_predict`, default `1024`) and
`think: false` for qwen3 model tags, which is what allows the thinking model
`qwen3:8b` to complete inside the read timeout.

### 2.6 Provider / LLM — EXTERNAL

Ollama on port 11434 is the verified provider. **Two models are validated
end-to-end:** `llama3` (default, 19.2s measured) and `qwen3:8b` (18.5s cold,
13.9s warm). The AI Engine's provider layer is abstracted, but only Ollama has
been exercised.

### 2.7 Symbols and relationships — PARTIAL

The models, controllers, services, and modules all exist and the routes respond
correctly. The services return `Promise.resolve([])`. The data structures are
real; the extraction and resolution are not written.

### 2.8 File analysis — PARTIAL

`GET /files/:id/analysis` returns a hardcoded object with `summary: undefined`
and `confidence: { level: 'low', model: 'none' }`. It echoes the path
parameter back as `requestId`. It performs no analysis.

### 2.9 Persistence — NOT IMPLEMENTED

There is **no** PostgreSQL integration: no client, no ORM, no migration, no
connection string handling, no repository layer. There is **no** Redis either.
Neither is imported anywhere in the backend.

A codebase-wide scan for these clients found nothing. Any future plan for them
is unimplemented, and this document does not claim otherwise.

### 2.10 Entity and feature modules — PARTIAL

`auth`, `users`, `organizations`, `projects`, `repositories`, `conversations`,
`documentation`, `tests`, and `onboarding` each declare a controller and a
module, but **no route handlers**. The controller files are 207–261 bytes —
class declarations and nothing else. They exist to fix the module graph shape,
not to serve traffic.

### 2.11 Containerisation and deployment — PARTIAL

`Dockerfile` per service and a root `compose.yaml` build and run the backend and
the AI Engine as a local, single-host, two-service stack. Both images are
multi-stage and run as non-root users. The only CI is
`.github/workflows/backend.yml`.

What does **not** exist: Kubernetes manifests, infrastructure-as-code, a
deployment pipeline, image registry publishing, TLS termination, or a reverse
proxy. The stack has no authentication, no TLS, and no rate limiting, so it must
not be exposed beyond `localhost`. See the
[deployment guide](../deployment/deployment-guide.md).

---

## 3. Backend internal structure

```
apps/api/src/
├── main.ts                     bootstrap; PORT, default 3000
├── app.module.ts               root module; APP_PIPE registered here
├── app.controller.ts           scaffold "Hello World!" route
├── common/                     cross-cutting, no business logic
│   ├── correlation/            X-Request-Id, AsyncLocalStorage, middleware
│   ├── logging/                AppLogger, allowlist redactor, sinks
│   └── validation/             single source of validation options
├── analysis/                   the real feature area
│   ├── analysis.controller.ts  POST /analysis/code, POST /analysis/file
│   ├── analysis.service.ts     provider-agnostic; no AI specifics
│   ├── adapters/               the only AI-aware layer
│   │   ├── ai-engine.adapter.ts
│   │   └── ai-engine.client.ts
│   ├── contracts/              frozen FastAPI request/response types
│   ├── config/                 AI_ENGINE_BASE_URL, AI_ENGINE_TIMEOUT_MS
│   ├── dto/                    validated request shapes
│   ├── interfaces/             IAnalysisProvider, ANALYSIS_PROVIDER
│   └── models/                 AnalysisResult, CodeSymbol, CodeRelationship
├── explanations/               POST /explanations, delegates to analysis
├── health/                     GET /health, GET /ready
├── files/ symbols/ relationships/   routes exist, data does not
└── auth/ users/ organizations/ …   empty module skeletons
```

### Why the adapter boundary matters

`analysis.service.ts` imports only `IAnalysisProvider`. Swapping the AI Engine
for a different provider means writing one new class and changing one module
registration. No controller, service, or DTO changes. The FastAPI request shape
appears in exactly one file.

---

## 4. Data flow for `POST /analysis/code`

1. `CorrelationIdMiddleware` reads `X-Request-Id`, validates it against
   `/^[A-Za-z0-9._~-]{1,128}$/`, and either adopts it or substitutes a UUID. It
   stores the value in `AsyncLocalStorage` and sets the response header **before**
   calling `next()`, so rejected requests still carry it.
2. The global `ValidationPipe` validates `AnalyzeCodeDto`. `code` is capped at
   100000 characters. Unknown properties are rejected with 400.
3. `AnalysisService.analyzeCode` reads the correlation ID (falling back to a
   random UUID) and calls the injected provider. It contains no AI specifics.
4. `AiEngineAdapterProvider` maps `AnalysisRequest` to the FastAPI request
   contract. `question` is always `null`; `analyses` is omitted entirely so the
   AI Engine applies its own default.
5. `AiEngineClient` POSTs with an `AbortController` armed at
   `AI_ENGINE_TIMEOUT_MS`.
6. The adapter maps the response: summary, confidence, and evidence are carried
   through. `symbols` and `relationships` are set to `[]` because the adapter
   does not populate them.
7. `AnalysisService` returns the `AnalysisResult`; the controller returns it.

---

## 5. Design decisions worth knowing

**Confidence is never strengthened.** The AI Engine's `CONFIRMED`, `INFERRED`,
and `UNKNOWN` map to `confirmed`, `inferred`, and `unknown`. They are not
collapsed into `high`/`medium`/`low`, because that would assert a strength the
AI Engine never claimed. `HIGH`/`MEDIUM`/`LOW` are still accepted in the
normaliser for older providers, and anything unrecognised becomes `unknown`
rather than a guess.

**Absent confidence is not zero.** The AI Engine supplies no numeric score, so
`score` stays `undefined`. It is never fabricated and `UNKNOWN` is never
converted to `0`.

**Evidence provenance is verbatim.** The AI Engine's `source_type` is stored in
`sourceType` unchanged. Reinterpreting `source_code` as `syntax`, for example,
would invent meaning the engine never asserted.

**Logging is deny-by-default.** `ALLOWED_LOG_FIELDS` is a seven-name allowlist. A
key not on it is never read, so it cannot leak even if a caller passes it.

**Timeouts reflect measurement.** `AI_ENGINE_TIMEOUT_MS` defaults to 60000
because real analyses were measured at 19.2s (`llama3`) and 18.5s (`qwen3:8b`
cold) on CPU-only hardware, with a 27.3s `llama3` run also seen. It matches the
AI Engine's own 60s provider budget, so it is an upper bound on the round trip
rather than an invented number.

---

## 6. Not implemented, and not to be assumed

- No database, no cache, no queue.
- No authentication, authorization, or rate limiting.
- No WebSocket or streaming. All responses are single JSON documents.
- No symbol extraction or relationship resolution.
- No deployment automation, registry publishing, or TLS termination. The Docker
  Compose stack is a local development stack only.
- No CI for the AI Engine or the extension.
- No **automated** multi-service E2E test in CI. The real chain
  (extension client → backend → AI Engine → Ollama) has been exercised manually
  and is reproducible, but nothing asserts it on every commit.
- `X-Request-Id` is not forwarded to the AI Engine, so its logs cannot be joined
  to a backend request ID. The backend-facing contract is unaffected.
