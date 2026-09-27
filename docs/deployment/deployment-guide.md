# Deployment Guide

**Current state: local Docker Compose stack for the backend and the AI Engine.
No deployment automation exists.**

Compose is a **local, single-host development** stack, not a production
deployment. There is no authentication, no TLS, and no rate limiting, so
binding these ports to anything other than `localhost` exposes an unmetered,
anonymous LLM proxy. See section 8.

---

## 1. What is NOT implemented

Stated explicitly so nothing here is mistaken for existing capability:

| Item | Status |
|---|---|
| Kubernetes manifests / Helm | **Does not exist** |
| Infrastructure-as-code (Terraform, Pulumi) | **Does not exist** |
| Deployment pipeline (CD) | **Does not exist** |
| Release / publish automation | **Does not exist** |
| Secrets manager integration | **Does not exist** |
| Reverse proxy configuration | **Does not exist** |
| TLS termination | **Does not exist** |
| Image registry publishing | **Does not exist** — images are built locally only |
| Containerised Ollama | **Deliberately not done** — Ollama stays on the host |
| Containerised extension / frontend | **Deliberately not done** |

---

## 2. What IS implemented

| Item | Status |
|---|---|
| `compose.yaml` (root) | Backend + AI Engine, two services, healthchecked |
| `Dockerfile` (backend, `apps/api`) | Multi-stage; non-root `node` user; image `HEALTHCHECK` |
| `Dockerfile` (AI Engine, `apps/ai-engine`) | Single-stage; non-root `appuser` UID 10001 |
| `.dockerignore` for both build contexts | Excludes `node_modules/`, `dist/`, `tests/`, and all `.env*` |
| `.env.example` (root) | Optional host-port / model overrides. No credentials |
| Liveness endpoint | `GET /health` on both services |
| Readiness endpoint | `GET /ready` on both services (configuration-only — see 4.3) |
| Backend CI (`.github/workflows/backend.yml`) | Lint, unit, E2E, build on Node 22 |

The AI Engine source is owned by Member 3 and was imported from
`origin/feature/member3-ai` at `1c73b34`, including its own `Dockerfile`. That
file was not authored here.

---

## 3. Container topology

```
host
├── Ollama            :11434   host process, NOT containerised
│        ▲
│        │ host.docker.internal (mapped via extra_hosts)
│        │
└── Docker Compose network
    ├── ai-engine      :8000    FastAPI, non-root appuser
    │        ▲
    │        │ service name "ai-engine"
    │        │
    └── api            :3000    NestJS, non-root node
             ▲
             └── published to the host for local clients
```

`api` never contacts Ollama. It only proxies to `ai-engine`.

There is no Compose service for Ollama and none for the extension.

---

## 4. Running the stack

**Requires Docker Desktop** with the daemon running. Ollama runs on the host.

### 4.1 Start

```bash
ollama serve            # if not already running
ollama list             # must list llama3:latest

docker compose up --build
docker compose ps
```

Shut down with `docker compose down`. Images are retained.

### 4.2 Host ports

Container ports are fixed by the service contract; only the host side of the
published mapping is adjustable, so the stack does not collide with a
development process already bound to `3000` or `8000`.

| Service | Container | Default host | Override |
|---|---|---|---|
| `api` | `3000` | `3002` | `API_HOST_PORT` |
| `ai-engine` | `8000` | `8002` | `AI_ENGINE_HOST_PORT` |

Set them in a gitignored `.env` (`cp .env.example .env`) to claim `3000`/`8000`
when free.

### 4.3 Health checks

Both Compose healthchecks target `/health`, never `/ready`.

| Service | Probe | Tooling | Why |
|---|---|---|---|
| `api` | `GET /health` on `127.0.0.1:3000` | Node global `fetch` | `node:22-slim` has no curl/wget |
| `ai-engine` | `GET /health` on `127.0.0.1:8000` | Python stdlib `urllib` | image has no curl/wget |

`/ready` was rejected as a probe for a specific reason: the AI Engine's
`/ready` makes **no LLM call**. It checks only that `PROVIDER` is a non-empty
string, so it answers `200` even with Ollama stopped or the model missing. The
backend's `/ready` proxies it and inherits the same weakness. A `/ready` probe
would therefore mark a stack healthy while every real analysis request fails.

`/health` is the honest container probe: it proves the process is up and
performs no network I/O, so a downstream slowdown cannot cause a restart loop.

**A `200` from `/ready` is not proof that Ollama is working.** The only proof is
a real analysis request (section 5).

---

## 5. Verifying a real end-to-end analysis

Liveness proves the process started. Only a real request proves the LLM path
works.

```bash
curl -X POST http://localhost:3002/analysis/code \
  -H 'Content-Type: application/json' \
  -d '{"language":"python","code":"def add(a, b):\n    return a + b\n"}'
```

The request flows: client → `api` container → NestJS controller and service →
`AiEngineAdapterProvider` → `ai-engine` container → host Ollama → `llama3` →
back. A `summary` in the response body is the proof that a model answered;
a `503` or `504` means it did not.

Expect tens of seconds on CPU-only hardware — about 34 seconds was measured for
`llama3`. Both timeouts are budgeted at 60 seconds
(`AI_ENGINE_TIMEOUT_MS`, `REQUEST_TIMEOUT`).

### Verified model: `llama3`

`llama3` is the model verified end-to-end. **Do not substitute `qwen3:8b`.**

> **Known limitation — `qwen3:8b` live timeout (unfixed, Member 3 owned).**
> `qwen3:8b` is a thinking model. Its reasoning trace arrives in
> `message.thinking`, which `OllamaProvider.complete` discards, and the provider
> sends no generation cap, so with `stream: False` generation cannot complete
> inside the read timeout. A real request burns the full `REQUEST_TIMEOUT` and
> returns `504 PROVIDER_TIMEOUT`.
>
> The defect is in the AI Engine's provider layer, is acknowledged in
> `apps/ai-engine/tests/integration/test_failure_states.py` and
> `tests/integration/__init__.py`, and is **not** worked around anywhere in this
> repository. It is a provider defect, not a Compose, networking, or Dockerfile
> fault. No timeout was silently increased to hide it.

---

## 6. AI Engine configuration in Compose

`compose.yaml` sets these; see `.env.example` for the overridable subset.

| Variable | Value in Compose | Notes |
|---|---|---|
| `PROVIDER` | `ollama` | only implemented provider |
| `MODEL` | `llama3` | overridable via `AI_ENGINE_MODEL` |
| `PROVIDER_BASE_URL` | `http://host.docker.internal:11434` | **not** `localhost` — see below |
| `REQUEST_TIMEOUT` | `60` | overridable via `AI_ENGINE_REQUEST_TIMEOUT` |
| `PROVIDER_API_KEY` | *unset* | Ollama needs no key; never set it |
| `HOST` / `PORT` | *not set* | the image `CMD` hardcodes `--host 0.0.0.0 --port 8000`, so these are inert |

`host.docker.internal` is mapped explicitly via
`extra_hosts: ["host.docker.internal:host-gateway"]`. Docker Desktop provides
the name implicitly; the explicit mapping is what lets the same file work on
Docker Engine for Linux. Using `localhost:11434` inside the container points at
the container itself, and every analysis fails with `503 PROVIDER_UNAVAILABLE`.

The backend's `AI_ENGINE_BASE_URL` is `http://ai-engine:8000` — the Compose
service name, never `localhost` and never the published host port.

---

## 7. Container security posture

| Check | Result |
|---|---|
| Runtime user, `api` | `node` (UID 1000), stock non-root image user |
| Runtime user, `ai-engine` | `appuser` (UID 10001), created in the Dockerfile |
| `--privileged` | Not used |
| Build secrets in layers | None. `npm ci` with no token; no `ARG`/`ENV` secrets |
| `.env` / `.env.example` in build context | Excluded by both `.dockerignore` files |
| Test code in runtime images | Excluded (`tests/`, `test/`) |
| TLS verification | Untouched; nothing disabled |
| Insecure registry config | None |
| Exposed ports | `api` → host `3002`, `ai-engine` → host `8002`; both bound on all interfaces by Docker's default, so treat them as local-only |
| Secrets in `compose.yaml` | None; all values are literals or gitignored `.env` substitutions |

Both images are single-user and run without elevated privileges. Both are bound
to `0.0.0.0` on the host by Docker's default publish behaviour, which on a
laptop means the local network. Add a firewall rule before using this on a
shared network.

---

## 8. Security posture in a deployed context

Before exposing any of this beyond a developer machine, note the current gaps.
These are **limitations, not features**:

- **No authentication.** Every endpoint is anonymous.
- **No rate limiting.** `/analysis/code` is an unmetered path to an LLM. Anyone
  who can reach the port can drive arbitrary model load and exhaust the host.
- **No security headers.** `helmet` is not installed.
- **No CORS configuration.** Safe only because the intended client is an
  extension host, not a browser.
- **No TLS.** Both services speak plain HTTP, including the
  `api` → `ai-engine` hop across the Compose network.
- **No secret management.** Environment variables only. `.env` is gitignored,
  but nothing injects secrets at runtime.
- **No resource limits.** Neither service sets CPU or memory caps, so a runaway
  model call can exhaust the host.

The logging redaction allowlist *is* production-worthy and prevents source code,
credentials, and upstream error text from reaching logs.

---

## 9. Recommended order of work

Not implementation — just sequencing.

1. **Add authentication and rate limiting.** Without them, an exposed backend is
   an open, unmetered LLM proxy. This is the highest-priority gap.
2. **Fix the AI Engine's dotenv handling.** The AI Engine still ignores `.env`;
   Compose injects variables correctly, but the two config stories disagree.
3. **Resolve the `qwen3:8b` provider timeout** (Member 3). It is a provider-layer
   defect: send a generation cap and read `message.thinking`.
4. **Pin versions.** Add `.nvmrc` and a `pyproject.toml` with
   `requires-python`. Builds are currently not reproducible.
5. **Add resource limits and a read-only filesystem** to both Compose services.
6. **Add CI for the AI Engine** — `.github/workflows/ai-engine.yml` exists on
   `origin/feature/member3-ai` but is not on this branch.
7. **Then** consider deployment automation.
