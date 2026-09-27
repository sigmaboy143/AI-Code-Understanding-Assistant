# Deployment Guide

**Current state: manual startup only. No containerisation and no deployment
automation exist in this repository.**

This document describes how to run the services today. It does not describe a
deployment pipeline, because there is not one.

---

## 1. What is NOT implemented

Stated explicitly so nothing here is mistaken for existing capability:

| Item | Status |
|---|---|
| `Dockerfile` (backend) | **Does not exist** |
| `Dockerfile` (AI Engine) | **Does not exist** |
| `docker-compose.yml` | **Does not exist** |
| Kubernetes manifests / Helm | **Does not exist** |
| Infrastructure-as-code (Terraform, Pulumi) | **Does not exist** |
| Deployment pipeline (CD) | **Does not exist** |
| Release / publish automation | **Does not exist** |
| Secrets manager integration | **Does not exist** |
| Reverse proxy configuration | **Does not exist** |
| TLS termination | **Does not exist** |

A scan of every branch found no container or orchestration file anywhere.

---

## 2. What IS implemented

| Item | Status |
|---|---|
| Backend CI (`.github/workflows/backend.yml`) | Lint, unit, E2E, build on Node 22 |
| Manual backend startup | `npm run start:dev` / `npm run start:prod` |
| Manual AI Engine startup | `uvicorn app.main:app` |
| Liveness endpoint | `GET /health` |
| Readiness endpoint | `GET /ready` |

CI covers **only** `apps/api`. The AI Engine and the extension are not gated by
any workflow, on any branch.

---

## 3. Backend startup

### 3.1 Development

```bash
cd apps/api
npm ci
npm run start:dev
```

Binds `PORT`, default `3000`.

### 3.2 Production-style

```bash
cd apps/api
npm ci
npm run build
npm run start:prod        # node dist/main
```

### 3.3 Required environment

```bash
export PORT=3000
export AI_ENGINE_BASE_URL=http://127.0.0.1:8000
export AI_ENGINE_TIMEOUT_MS=60000
```

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `3000` | |
| `AI_ENGINE_BASE_URL` | `http://127.0.0.1:8000` | Bare origin, no trailing slash |
| `AI_ENGINE_TIMEOUT_MS` | `60000` | Must exceed real inference time (~34s measured) |

Full reference: [environment.md](../development/environment.md).

### 3.4 Health checking

| Probe | Endpoint | Success |
|---|---|---|
| Liveness | `GET /health` | `200 {"status":"ok"}` — no dependencies |
| Readiness | `GET /ready` | `200 {"status":"ready","aiEngine":"ok"}` |

Configure a liveness probe against `/health` and a readiness probe against
`/ready`. Liveness must never depend on the AI Engine, or a downstream outage
would cause a restart loop of a healthy process.

---

## 4. AI Engine startup

Not present in this checkout; developed on `feature/member3-ai`.

```bash
cd apps/ai-engine
pip install -r requirements.txt
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
export REQUEST_TIMEOUT=60
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| Variable | Default |
|---|---|
| `HOST` | `0.0.0.0` |
| `PORT` | `8000` |
| `PROVIDER` | `ollama` |
| `MODEL` | `llama3` |
| `PROVIDER_BASE_URL` | `http://localhost:11434` |
| `REQUEST_TIMEOUT` | `60` |
| `PROVIDER_API_KEY` | unset — cloud providers only |

> **Blocker for containerisation:** the AI Engine does not load `.env` files.
> `python-dotenv` is missing and `config.py` never calls `load_dotenv()`, so
> the documented `cp .env.example .env` step does nothing. Variables must be
> injected by the process environment. This must be fixed before a container
> image can be built with a sane config story.

---

## 5. Provider requirements

The backend is a proxy to an LLM. Something must be serving models.

### 5.1 Ollama (verified)

```bash
ollama serve
ollama pull llama3
```

- Default port `11434`
- `llama3` is the model verified end-to-end
- Expect tens of seconds per analysis on CPU-only hardware
- **A 34.3-second response was measured.** Any client or proxy timeout below
  that will fail

### 5.2 Cloud providers

The AI Engine's provider layer is abstract, but only Ollama has been exercised.
`PROVIDER_API_KEY` would be required. No cloud configuration has been validated.

---

## 6. Runtime topology today

```
Developer machine / server
├── Ollama            :11434   (external process)
├── AI Engine         :8000    (uvicorn, manual)
└── NestJS backend    :3000    (node, manual)
```

All three are on one host in every configuration that has been verified. Nothing
has been tested split across hosts, which means nothing is known about TLS,
firewalling, or inter-host latency.

---

## 7. Security posture in a deployed context

Before exposing any of this beyond a developer machine, note the current gaps.
These are **limitations, not features**:

- **No authentication.** Every endpoint is anonymous.
- **No rate limiting.** `/analysis/code` is an unmetered path to an LLM. Anyone
  who can reach the port can drive arbitrary model load and exhaust the host.
- **No security headers.** `helmet` is not installed.
- **No CORS configuration.** Safe only because the intended client is an
  extension host, not a browser.
- **No TLS.** Both services speak plain HTTP.
- **No secret management.** Environment variables only. `.env` is gitignored,
  but nothing injects secrets at runtime.

The logging redaction allowlist *is* production-worthy and prevents source code,
credentials, and upstream error text from reaching logs.

---

## 8. Recommended order of work

Not implementation — just sequencing, so containerisation is not attempted
against a moving target.

1. **Add authentication and rate limiting.** Without them, an exposed backend is
   an open, unmetered LLM proxy. This is the highest-priority gap.
2. **Fix the AI Engine's dotenv handling.** Required before a container image can
   have a coherent config story.
3. **Pin versions.** Add `.nvmrc` and a `pyproject.toml` with
   `requires-python`. Builds are currently not reproducible.
4. **Decide the merged repository layout.** The extension is rooted at the
   repository root on its branch; that has to be settled before any
   multi-service container or CI file can be written.
5. **Add CI for the AI Engine and the extension.**
6. **Then** write a `Dockerfile` and a compose file.
7. **Then** consider deployment automation.

Steps 6 and 7 depend on 1–4. Attempting them earlier would bake in assumptions
that have not been agreed.
