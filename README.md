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
VS Code Extension / React Webview        ← NOT PRESENT on this branch
   ↓
NestJS Backend  (apps/api, port 3000)    ← PRESENT
   ↓
AI Engine  (FastAPI, port 8000)          ← separate service, separate branch
   ↓
Ollama / LLM  (port 11434)
```

The backend is the only caller of the AI Engine, and the extension is intended to
be the only caller of the backend. No client ever talks to a model provider
directly.

> **Important:** only the middle two layers exist on this branch. The VS Code
> extension and the AI Engine are developed on their own branches
> (`feature/member2-vscode-frontend` and `feature/member3-ai`) and have **not**
> been merged here. Nothing in this repository at this commit can be run
> end-to-end from a single checkout.

### Implementation status at a glance

| Layer | State | Notes |
|---|---|---|
| NestJS backend | **Implemented** | Lint, build, 455 unit/integration tests, 5 E2E tests all pass |
| AI Engine | **Implemented** | In `apps/ai-engine`, imported from `origin/feature/member3-ai` at `1c73b34`. Owned by Member 3 |
| VS Code extension + React webview | **Separate branch** | Not in this checkout |
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

A separate FastAPI service, developed on `feature/member3-ai` (head
`3ee7824`). It is **not part of this checkout**.

Contract as verified against that branch:

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
origin (`source_code`, `retrieved_chunk`, `file`, `documentation`). As of
`3ee7824` it also populates `dependencies` deterministically by parsing Python
imports — but **the backend does not read that field yet**, so it is not
visible through the NestJS API.

---

## Verified integration

The following chain was exercised in a real runtime, not mocked:

```
NestJS  →  AiEngineAdapterProvider  →  FastAPI AI Engine  →  Ollama / llama3  →  NestJS
```

It completed with HTTP `201`, matching `X-Request-Id` correlation IDs on both
sides, and a real ~34s inference.

**What is *not* verified:** the full developer journey. Nobody has yet run
extension → backend → AI Engine → Ollama in one pass. The extension's HTTP
client is contract-correct against the backend, but it is untested against a
live backend — and its 30-second client timeout is **shorter** than the ~34s the
backend actually takes, so real-mode requests would currently abort client-side.
Fixing that is Member 2's task.

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

`AI_ENGINE_TIMEOUT_MS` is 60000 because a real `llama3` analysis was measured at
34.3s. The previous 10s default could not have succeeded against a live model.
This matches the AI Engine's own 60s provider budget.

### AI Engine (`apps/ai-engine`, separate branch)

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

Expect tens of seconds (~34s measured for `llama3` on CPU-only hardware).

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

> **Use `llama3`, not `qwen3:8b`.** `qwen3:8b` is a thinking model whose
> reasoning trace the AI Engine's provider discards, and no generation cap is
> sent, so a live request cannot finish inside the read timeout and returns
> `504`. It is a known, unfixed provider defect owned by Member 3, not a
> networking or Compose fault.

---

## Testing

| Suite | Command | Deterministic? |
|---|---|---|
| Backend unit + integration | `npm test` | **Yes** — fully mocked, no network |
| Backend E2E smoke | `npm run test:e2e` | **Yes** — no AI Engine, Ollama, or database |
| AI Engine unit | `python -m pytest` | **Yes** — uses a mock provider |

The backend E2E suite is deliberately independent of every external service. It
has been verified to pass with `AI_ENGINE_BASE_URL` pointed at a dead port.

Details: [docs/testing/testing-guide.md](docs/testing/testing-guide.md).

---

## Repository structure

What exists on this branch:

```
.
├── apps/
│   └── api/                  NestJS backend (the only app here)
├── docs/                     Documentation (see below)
├── .github/workflows/
│   └── backend.yml           Backend CI
├── .gitignore
└── README.md
```

What does **not** exist here but exists on other branches:

- `feature/member2-vscode-frontend` — the extension's `package.json` sits at the
  **repository root** on that branch, with `src/` and `webview-ui/`
- `feature/member3-ai` — `apps/ai-engine/`

Because the extension is rooted at the repository root on its branch, the final
merged layout has not been decided yet.

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
- The AI Engine's `dependencies` output is not read by the backend adapter.
- The extension is not merged, so there is no single-checkout run that includes
  the VS Code client. The extension's 30s client timeout is below the backend's
  real ~34s latency.
- AI answer quality has not been systematically evaluated.
- Docker Compose is a **local, single-host development** stack only. No
  deployment automation, no registry publishing, no database. It has no
  authentication, no TLS, and no rate limiting, so it must not be exposed
  beyond `localhost`.
- Ollama is not containerised; it runs on the host and is reached from the
  `ai-engine` container via `host.docker.internal`.
- `GET /ready` on both services reports configuration readiness only. It never
  contacts Ollama, so it is not evidence that the LLM path works.
- `qwen3:8b` times out against a live provider (thinking model, discarded
  reasoning trace, no generation cap). Unfixed, Member 3 owned. `llama3` is the
  verified model.
- CI covers the backend only. `.github/workflows/ai-engine.yml` exists on
  `origin/feature/member3-ai` but is not on this branch.
- The `context` request field has no maximum length, and `/explanations`
  performs no field validation of its own.

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
