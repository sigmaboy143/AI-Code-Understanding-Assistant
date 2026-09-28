# AI-Powered Code Understanding & Developer Assistant

A tool for understanding **existing** code with AI, rather than primarily using
AI to generate new code.

Most AI coding tools optimise for writing. This project optimises for reading:
given a selection or a file that someone else wrote, explain what it does, show
the evidence behind that explanation, and be honest when the evidence is weak.

---

## Current architecture

```
Developer
   ↓
VS Code Extension / React Webview        ← PRESENT, src/ + webview-ui/
   ↓
NestJS Backend  (apps/api, port 3000)    ← PRESENT
   ↓
AI Engine  (FastAPI, port 8000)          ← PRESENT, apps/ai-engine @ 04faea5
   ↓
Ollama / LLM  (port 11434)               ← host process, not containerised
```

The backend is the only caller of the AI Engine, and the extension is intended to
be the only caller of the backend. No client ever talks to a model provider
directly.

> **Scope of this branch:** all three layers — the VS Code extension, the backend,
> and the AI Engine — now live in this checkout. The extension's `package.json` is
> at the **repository root** (not under `apps/`), so the extension, the backend,
> and the webview are three separate `package.json` roots; see
> [Repository structure](#repository-structure).

### Implementation status at a glance

| Layer | State | Notes |
|---|---|---|
| NestJS backend | **Implemented** | Lint, build, 455 unit/integration tests, 5 E2E tests all pass |
| AI Engine | **Implemented** | In `apps/ai-engine`, synchronised from `origin/feature/member3-ai` at `04faea5`. Owned by Member 3. 870 tests pass |
| VS Code extension + React webview | **Implemented** | At the repository root: `src/` (extension host) + `webview-ui/` (React). Merged from `origin/feature/member2-vscode-frontend` |
| Ollama | **External** | Host process on `11434`; deliberately not containerised. `llama3` and `qwen3:8b` both validated |
| PostgreSQL | **Not implemented** | No code, no client, no migration |
| Redis | **Not implemented** | No code, no client |
| Docker | **Implemented** | `Dockerfile` per service + root `compose.yaml`. Local single-host stack only |
| CI/CD | **Partial** | One workflow; backend only |

---

## Current backend — `apps/api`

NestJS 12, TypeScript, Express. Listens on port **3000** by default.

```bash
cd apps/api
npm ci
npm run start:dev
```

| Task | Command |
|---|---|
| Install | `npm ci` |
| Start (watch) | `npm run start:dev` |
| Build | `npm run build` |
| Start (built) | `npm run start:prod` |
| Lint | `npm run lint` |
| Unit/integration tests | `npm test` |
| E2E tests | `npm run test:e2e` |

### Endpoints

Operational:

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/health` | Liveness. Always `200 {"status":"ok"}`. Performs **no** network I/O. |
| `GET` | `/ready` | Readiness. `200 {"status":"ready","aiEngine":"ok"}` when the AI Engine reports ready, otherwise `503 {"status":"not_ready","aiEngine":"unavailable"}`. |

AI-backed analysis (these call the AI Engine):

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/analysis/code` | Analyses a code string. **Implemented.** |
| `POST` | `/analysis/file` | Analyses a whole file. **Implemented.** |
| `POST` | `/explanations` | Analyses code and returns an explanation-shaped response. **Implemented.** |

Present but **not yet functional** — the route exists and returns `200`, but the
data is fixed or empty:

| Method | Path | Actual behaviour today |
|---|---|---|
| `GET` | `/files/:id/analysis` | Returns a hardcoded stub. `summary` is `undefined`, confidence is `low` with `model: "none"`. It does **not** analyse anything. |
| `GET` | `/symbols?filePath=&language=` | Always returns `[]`. |
| `GET` | `/relationships?filePath=&language=` | Always returns `[]`. |

`GET /` still returns the NestJS scaffold string `"Hello World!"`. It is
leftover scaffolding, not a feature.

Nine modules — `auth`, `users`, `organizations`, `projects`, `repositories`,
`conversations`, `documentation`, `tests`, `onboarding` — declare a controller
with **zero route handlers**. They are module skeletons. Calling them returns
`404`; no code exists to serve them.

### Response shape

`POST /analysis/code` and `POST /analysis/file` return:

```jsonc
{
  "requestId": "…",          // echoes the X-Request-Id correlation ID
  "language": "typescript",
  "symbols": [],             // always empty — extraction not implemented
  "relationships": [],       // always empty — resolution not implemented
  "summary": "…",            // from the AI Engine
  "confidence": {
    "level": "confirmed",    // confirmed | inferred | unknown | low | medium | high
    "score": undefined,      // omitted; the AI Engine supplies no numeric score
    "model": "…",
    "reasoning": "…"
  },
  "evidence": [
    {
      "kind": "source_code", // AI Engine source_type, carried through verbatim
      "detail": "…",
      "sourceType": "source_code",
      "filePath": "…",
      "lineStart": 1,
      "lineEnd": 10,
      "chunkId": null
    }
  ],
  "analysedAt": "2026-01-01T00:00:00.000Z"
}
```

Confidence and evidence are **never invented**. If the AI Engine reports
`UNKNOWN`, the backend returns `unknown` and omits the score rather than
substituting `0`.

---

## AI Engine

A separate FastAPI service living in `apps/ai-engine`, synchronised from
`feature/member3-ai` at `04faea5`. It runs in the same checkout as the backend.

Contract as verified against that commit:

| Item | Value |
|---|---|
| Base URL (local) | `http://127.0.0.1:8000` |
| Analysis endpoint | `POST /api/v1/code-understanding` |
| Liveness | `GET /health` |
| Readiness | `GET /ready` |
| Auth | None |
| Request timeout | `REQUEST_TIMEOUT`, default 60s |

It returns a plain-language `summary`, a three-state `confidence`
(`CONFIRMED` / `INFERRED` / `UNKNOWN`), and evidence items tagged with their
origin (`source_code`, `retrieved_chunk`, `file`, `documentation`). It also
populates `dependencies` deterministically by parsing Python `import` statements
with `ast` — never by reading dependency names out of model output. The backend
does **not** read that field yet, so it is not visible through the NestJS API;
see [Integration Contracts](docs/architecture/integration-contracts.md).

---

## Verified integration

The following chain was exercised in a real runtime, not mocked:

```
NestJS  →  AiEngineAdapterProvider  →  FastAPI AI Engine  →  Ollama  →  NestJS
```

Measured against a live host Ollama, through the Docker Compose stack:

| Model | Result | Latency |
|---|---|---|
| `llama3` (default) | `201` | 19.2s (27.3s on an earlier run) |
| `qwen3:8b` | `201` | 18.5s cold, 13.9s warm |

Both returned `confidence.level = "unknown"` with **no numeric score**, one
`source_code` evidence item, and empty `symbols` / `relationships` — nothing
invented. The AI Engine logs confirm the real provider call
(`provider=OllamaProvider model=llama3` / `model=qwen3:8b`) and an HTTP `200`
from `host.docker.internal:11434`.

The extension's client code was additionally exercised **headlessly** against
this running backend — its unmodified `apiService` and analysis adapter — with
15/15 assertions passing, including that `unknown` confidence is not upgraded
and that no symbols or relationships are fabricated when the backend sends none.
Its 70s client timeout deliberately exceeds the backend's 60s budget, so a slow
but successful analysis is not misreported as a client-side timeout.

**Known gap:** the `X-Request-Id` correlation ID is **not** propagated across
the backend → AI Engine hop. The backend sends only `Content-Type`, so the AI
Engine mints its own ID. A client sees one consistent ID (header, body, and
backend logs all agree); the AI Engine's log line carries a different one.
Traced with `apps/api/src/analysis/adapters/ai-engine.client.ts:92`.

---

## VS Code extension — `src/` and `webview-ui/`

A VS Code extension that explains selected code and whole files, and surfaces the
confidence and evidence behind each answer. The extension is the only client of
the backend; the backend is the only caller of the AI Engine.

Its `package.json` is at the **repository root**, so the extension builds with
`npm install` in the repo root — not inside `apps/api`.

### Features

- **Explain Selected Code** — analyses the current selection via `POST /analysis/code`
- **Explain File** — analyses the complete active document via `POST /analysis/file`
- **Relations** — resolves relationships for a file via `GET /relationships`
- Activity Bar side panel plus a standalone editor panel
- Confidence and evidence rendered from the backend's own values, never invented

### Panel tabs: real vs mock

The backend currently implements only a few features. The other tabs are kept in
the UI as clearly-labelled placeholders rather than being removed, and they never
issue a request to a URL that does not exist.

| Tab | Real backend | Endpoint | Notes |
| --- | --- | --- | --- |
| Explain | Yes | `POST /analysis/code`, `POST /analysis/file` | Real result when mock mode is off |
| Relations | Yes | `GET /relationships?filePath&language` | Route is real; the backend's resolver currently returns an empty array |
| Why | No | — | Backend capability not currently available |
| Data | No | — | Backend capability not currently available |
| History | No | — | Backend capability not currently available |
| Impact | No | — | Backend capability not currently available |
| Tests | No | — | Backend capability not currently available |
| Debug | No | — | Backend capability not currently available |
| Arch | No | — | Backend capability not currently available |
| Search | No | — | Demo only; results are fixed strings, not real matches |
| Chat | No | — | Demo only; replies are placeholders, not analysis |

"Backend capability not currently available" is not an error state. Nothing was
requested and nothing failed — the feature simply has no HTTP route yet. The
`conversations`, `tests`, `documentation`, `onboarding`, `auth`, `users`,
`organizations`, `projects` and `repositories` controllers are declared in the
backend but declare no route handler, and impact / debugging / architecture / git
exist only as injectable services with no controller.

### Requirements

- VS Code `^1.138.0`
- For real (non-mock) mode: the NestJS backend running and reachable. The
  extension never calls an AI provider directly.

### Extension Settings

* `aicode.useMockData` — when `true` (the default) every tab returns locally
  generated demo data and no HTTP request is made. Set it to `false` to talk to
  the real backend.
* `aicode.backendUrl` — base URL of the backend. Defaults to
  `http://localhost:3000`. A trailing slash is tolerated.
* `aicode.explanationMode` — default explanation depth: `beginner`,
  `intermediate` or `advanced`.

### Running the extension

```bash
npm install
npm run build-webview   # builds the React webview into webview-ui/dist
npm run compile         # compiles the extension host to out/
```

Then press <kbd>F5</kbd> to launch an Extension Development Host.

To run the webview in a plain browser for UI work:

```bash
npm run watch-webview
```

Outside VS Code there is no extension host, so no backend call can be made; the
webview logs outgoing messages to the console instead.

> The root `npm install` installs the extension and the webview. The backend is a
> **separate** install under `apps/api` — run `npm ci` there too. Do not confuse
> the two `node_modules` trees.

### Extension tests

```bash
npm run test:unit       # contract/adapter unit tests, no VS Code required
npm test                # extension-host tests (downloads VS Code on first run)
```

`npm test` downloads and launches a VS Code build, so it is not a headless
command.

### Correlation

Each real request carries an `X-Request-Id` header. The backend's correlation
middleware honours it and always echoes one back, so the ID shown under an
Explain result is the backend's own correlation ID and can be quoted when
reporting a problem.

### Extension known issues

- Every tab other than Explain and Relations is a placeholder, for the reasons
  in the table above. They are not wired to the backend because no endpoint
  exists to wire them to.
- `GET /relationships` is real but its service resolves to an empty array, so
  the Relations tab legitimately shows "no relationships" against a live backend.
- A real analysis returns one `summary`. The What / How / Why sections remain in
  the panel, but How and Why state that the backend did not provide them rather
  than being filled with generated prose.
- The backend caps `code` at 100000 characters. Selecting more than that is
  reported before the request is sent.

---

## Environment

No credentials are stored in this repository. `.env` and `.env.*` are
gitignored, with `.env.example` allowed.

### Backend (`apps/api`)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | Port the NestJS server binds. |
| `AI_ENGINE_BASE_URL` | `http://127.0.0.1:8000` | Where the AI Engine is listening. |
| `AI_ENGINE_TIMEOUT_MS` | `60000` | How long to wait for one AI Engine call. |

`AI_ENGINE_TIMEOUT_MS` is 60000 because a real analysis was measured at 19.2s
for `llama3` and 18.5s for `qwen3:8b` on CPU-only hardware, with a slower 27.3s
`llama3` run also observed. The previous 10s default could not have succeeded
against a live model. 60000 matches the AI Engine's own 60s provider budget, so
the backend's limit is an honest upper bound on the round trip.

### AI Engine (`apps/ai-engine`)

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address. |
| `PORT` | `8000` | Bind port. |
| `PROVIDER` | `ollama` | Provider selection. |
| `MODEL` | `llama3` | Model name forwarded to the provider. |
| `PROVIDER_BASE_URL` | `http://localhost:11434` | Ollama's default port. |
| `REQUEST_TIMEOUT` | `60` | Seconds to wait for the provider. |
| `PROVIDER_API_KEY` | unset | Only for cloud providers. Never needed for Ollama. |

> Known issue: the AI Engine does not currently load a `.env` file, so copying
> `.env.example` to `.env` has no effect. Environment variables must be exported
> by the shell for now.

Full detail: [docs/development/environment.md](docs/development/environment.md).

---

## Local development

Two supported paths. The Compose path is recommended; the bare-metal path is
kept for debugging.

### Option A — Docker Compose (recommended)

Requires **Docker Desktop**. Ollama stays on the **host** and is not
containerised.

**1. Start Ollama and confirm the model**

```bash
ollama serve
ollama list              # must list llama3:latest
```

**2. Build and start the backend and the AI Engine**

```bash
docker compose up --build
docker compose ps
```

**3. Verify**

```bash
curl http://localhost:3002/health     # {"status":"ok"}
curl http://localhost:8002/health     # {"status":"ok"}
```

**4. Real end-to-end analysis** — this is the only check that proves the LLM
path works, because it actually calls `llama3` on the host:

```bash
curl -X POST http://localhost:3002/analysis/code \
  -H 'Content-Type: application/json' \
  -d '{"language":"python","code":"def add(a, b):\n    return a + b\n"}'
```

Expect tens of seconds on CPU-only hardware — 19.2s measured for `llama3`,
18.5s for a cold `qwen3:8b` and 13.9s once warm. Both models are validated;
`llama3` is the default.

Shut down with `docker compose down`. Host ports default to `3002` / `8002` to
avoid colliding with a local process on `3000` / `8000`; override with
`API_HOST_PORT` / `AI_ENGINE_HOST_PORT` in a gitignored `.env`
(`cp .env.example .env`).

Full details: [deployment guide](docs/deployment/deployment-guide.md).

### Option B — no containers

Backend and AI Engine run directly on the host.

**1. Start Ollama and pull the model**

```bash
ollama serve
ollama pull llama3
```

**2. Start the AI Engine**

```bash
cd apps/ai-engine
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**3. Start the backend**

```bash
cd apps/api
npm ci
npm run start:dev
```

**4. Verify**

```bash
curl http://127.0.0.1:8000/health     # {"status":"ok"}
curl http://127.0.0.1:3000/health     # {"status":"ok"} — no AI Engine needed
```

> **`/ready` is configuration readiness only.** The AI Engine's `/ready` makes
> no LLM call — it checks only that `PROVIDER` is a non-empty string, so it
> returns `200` even when Ollama is stopped or the model is missing. A `200`
> from `/ready` is **not** proof that Ollama is working. Only a real analysis
> request proves that. This is why the Compose healthchecks use `/health`.

> **Both `llama3` and `qwen3:8b` are validated.** Earlier revisions of the AI
> Engine could not serve `qwen3:8b` within the read timeout, because that model
> is a *thinking* model whose reasoning trace the provider discarded while
> sending no generation cap, so a live request burned the full budget and
> returned `504`. The synchronised AI Engine at `04faea5` fixes this: it now
> sends `think: false` for qwen3 model tags and always sends a generation cap
> (`num_predict`, default `1024`). Live `qwen3:8b` requests complete in
> 13.9–18.5s. See [Verified integration](#verified-integration).

To switch models, use the supported Compose override rather than editing files:

```bash
AI_ENGINE_MODEL=qwen3:8b docker compose up -d --force-recreate ai-engine
docker compose exec ai-engine python3 -c "from app.config import settings; print(settings.model)"
```

---

## Testing

| Suite | Command | Run from | Deterministic? |
|---|---|---|---|
| Backend unit + integration | `npm test` | `apps/api` | **Yes** — fully mocked, no network (19 suites, 455 tests) |
| Backend E2E smoke | `npm run test:e2e` | `apps/api` | **Yes** — no AI Engine, Ollama, or database (1 suite, 5 tests) |
| AI Engine unit + integration | `python -m pytest` | `apps/ai-engine` | **Yes** — uses a mock provider (29 files, 870 tests) |
| Extension contract/adapter unit | `npm run test:unit` | repo root | **Yes** — no VS Code download required |
| Extension host tests | `npm test` | repo root | **No** — downloads and launches VS Code |
| Live end-to-end | the curl in [Option A](#option-a--docker-compose-recommended) | repo root | **No** — real Ollama required |

The backend E2E suite is deliberately independent of every external service. It
has been verified to pass with `AI_ENGINE_BASE_URL` pointed at a dead port.

> `npm test` means **two different things** depending on your working directory:
> in `apps/api` it is the Jest backend suite; at the repository root it is the
> VS Code extension-host suite. Use `npm run test:unit` at the root for the
> headless option.

Details: [docs/testing/testing-guide.md](docs/testing/testing-guide.md).

---

## Repository structure

What exists in this branch:

```
.
├── apps/
│   ├── api/                  NestJS backend (TypeScript, port 3000)
│   └── ai-engine/            FastAPI AI Engine (Python 3.11, port 8000)
├── src/                      VS Code extension host (TypeScript)
├── webview-ui/               React webview client (Vite)
├── .vscode/                  Extension launch/debug configuration
├── docs/                     Documentation (see below)
├── .github/workflows/
│   ├── backend.yml           Backend CI
│   └── ai-engine.yml         AI Engine CI
├── package.json              Extension + webview (repo root) — NOT the backend
├── tsconfig.json             Extension TypeScript config
├── .env.example              Optional Compose overrides, no credentials
├── .gitignore
├── compose.yaml              Backend + AI Engine, two services
└── README.md
```

> **Three separate `package.json` roots.** The extension and webview build from
> the **repository root**; the backend builds from **`apps/api`**. They are not a
> workspace and do not share `node_modules`.

### Where each member's work landed

| Owner | Branch merged | Landed at |
|---|---|---|
| Member 1 | `feature/member1-backend-core-intelligence` | `apps/api/`, `docs/`, `compose.yaml`, `.github/workflows/backend.yml` |
| Member 2 | `feature/member2-vscode-frontend` | `src/`, `webview-ui/`, `.vscode/`, root `package.json`, `tsconfig.json` |
| Member 3 | `feature/member3-ai` | `apps/ai-engine/` (already byte-identical to M1's copy) plus `AGENTS.md`, `.bob/`, `.github/workflows/ai-engine.yml` |
| Member 4 | `feature/member4-integration-devops` | already contained in `feature/member3-ai`, so nothing new to merge |

---

## Security

Current posture, stated plainly:

**In place**

- `.env` and `.env.*` are gitignored; `.env.example` is allowlisted.
- No credentials are committed. A scan of all tracked files found no API keys,
  tokens, passwords, private keys, or cloud credentials.
- Backend logging is **allowlist-based**. Exactly seven field names
  (`operation`, `path`, `status`, `durationMs`, `code`, `requestId`, `outcome`)
  are ever read from a log call; anything else is dropped rather than filtered.
  Source code, request bodies, response bodies, URL credentials, and query
  strings cannot reach a log line. This is covered by roughly 60 tests.
- Upstream error messages from the AI Engine are never forwarded to API callers.
- `X-Request-Id` is validated against `/^[A-Za-z0-9._~-]{1,128}$/`; anything
  else is replaced with a fresh UUID, which blocks header injection and log
  forging.

**Not in place — current limitations, not completed features**

- **No authentication.** Every endpoint is anonymous.
- **No authorization.** No guards of any kind.
- **No rate limiting.** `/analysis/code` is an unauthenticated, unmetered path
  to an LLM. This is the most exposed gap.
- **No security headers.** `helmet` is not installed.
- **No CORS configuration.** Currently safe only because the intended client is
  a VS Code extension host, not a browser.
- `npm audit` reports 5 advisories, all inside `@nestjs/mau` — a **devDependency**
  used only by the deploy CLI. `npm audit --omit=dev` reports **0**.

---

## Known limitations

- Nine backend modules are empty skeletons; their controllers register no routes.
- `symbols` and `relationships` always return `[]`; extraction and resolution
  are not implemented.
- `GET /files/:id/analysis` returns hardcoded placeholder data.
- `POST /explanations` always returns `detailed: undefined` and
  `referencedSymbols: []`.
- The AI Engine's `dependencies` output is populated but not read by the backend
  adapter, so it is invisible through the NestJS API. The AI Engine also emits an
  `error_explanation` field that the backend's response contract does not
  declare, so it is dropped.
- **`X-Request-Id` is not propagated to the AI Engine.** The backend sends only
  `Content-Type`, so the AI Engine mints a separate ID. A client still sees one
  consistent ID across header, body, and backend logs.
- The extension, the backend, and the webview are three separate
  `package.json` roots. The extension's `package.json` sits at the repository
  root rather than under `apps/`, so no single `npm install` covers everything
  and there is no workspace linking them.
- The extension's full `vscode-test` GUI suite was not executed; it downloads and
  launches VS Code. Headless lint, compile, webview build, unit tests, and a live
  client test all passed.
- AI answer quality has not been systematically evaluated.
- Docker Compose is a **local, single-host development** stack only. No
  deployment automation, no registry publishing, no database. It has no
  authentication, no TLS, and no rate limiting, so it must not be exposed
  beyond `localhost`.
- Ollama is not containerised; it runs on the host and is reached from the
  `ai-engine` container via `host.docker.internal`.
- `GET /ready` on both services reports configuration readiness only. It never
  contacts Ollama, so it is not evidence that the LLM path works.
- CI covers the backend only. `.github/workflows/ai-engine.yml` exists on
  `origin/feature/member3-ai` but is not on this branch.
- The `context` request field has no maximum length, and `/explanations`
  performs no field validation of its own.
- There is no automated multi-service E2E test in CI. The real multi-service
  path has been exercised manually and is reproducible with the curl above.

---

## Technologies

| Layer | Technology |
|---|---|
| Backend | NestJS 12, TypeScript (ESM), Express, Jest, `oxlint` |
| AI Engine | Python 3.11+, FastAPI, Uvicorn, Pydantic, `httpx`, pytest |
| LLM runtime | Ollama (host process) with `llama3` and `qwen3:8b` |
| Extension | TypeScript, VS Code extension host, React 18, Zustand, Vite, axios |
| Packaging | Docker (multi-stage images), Docker Compose |
| CI | GitHub Actions (backend) |

**Not used at runtime:** IBM watsonx.ai and watsonx Orchestrate. The only model
provider exercised in this repository is a local Ollama instance. The AI Engine
does define a `PROVIDER` abstraction, but no watsonx provider implementation has
been written or verified here.

---

## Team and contribution structure

Work is split across four feature branches. This branch,
`integration/hackathon-final`, is the integration branch for all of them.

| Owner | Branch merged | Contribution | State here |
|---|---|---|---|
| Member 1 | `feature/member1-backend-core-intelligence` | NestJS backend, AI Engine integration, Docker/Compose, CI, documentation | **merged** |
| Member 2 | `feature/member2-vscode-frontend` | VS Code extension and React webview client | **merged** (unrelated root history; `--allow-unrelated-histories` required) |
| Member 3 | `feature/member3-ai` | FastAPI AI Engine, Ollama provider, evidence/confidence model | **merged** (`apps/ai-engine` was already byte-identical; this added `AGENTS.md`, `.bob/`, and the AI Engine CI workflow) |
| Member 4 | `feature/member4-integration-devops` | Code intelligence, explanation/git-reasoning/debug/impact agents | **already contained** in `feature/member3-ai`, so merging it would have been a no-op |

The VS Code extension keeps its `package.json` at the **repository root** rather
than under `apps/`. That hybrid layout is the result of merging the branches as
they stand; relocating it into `apps/extension/` would be a separate change.

`feature/member1-vscode` is empty (identical to the original `main`) and was not
merged.

---

## Documentation

| Document | Contents |
|---|---|
| [System Architecture](docs/architecture/system-architecture.md) | Layer-by-layer design, implementation status |
| [Integration Contracts](docs/architecture/integration-contracts.md) | Verified request/response contracts between layers |
| [Environment](docs/development/environment.md) | Variables, ports, version requirements |
| [Testing Guide](docs/testing/testing-guide.md) | Every command, and what is deterministic |
| [Deployment Guide](docs/deployment/deployment-guide.md) | Current startup; what is not implemented |
| [Troubleshooting](docs/development/troubleshooting.md) | Known problems and fixes |
| [Backend README](apps/api/README.md) | Backend-specific reference |
| [AI Engine README](apps/ai-engine/README.md) | AI Engine reference: providers, agents, evidence, observability |
