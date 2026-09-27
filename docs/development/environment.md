# Environment

Ports, variables, and version requirements. No real credentials appear in this
document; every value below is either a default from source code or a safe
placeholder.

---

## 1. Ports

| Service | Port | Source |
|---|---|---|
| NestJS backend | `3000` | `main.ts`, `process.env.PORT ?? 3000` |
| FastAPI AI Engine | `8000` | AI Engine default |
| Ollama | `11434` | AI Engine `PROVIDER_BASE_URL` default |

Running both processes directly on the host, the backend reaches the AI Engine
over HTTP on `127.0.0.1:8000` by default, and the AI Engine reaches Ollama on
`localhost:11434`.

Under Docker Compose these three addresses are **not** interchangeable with
`localhost`, because inside a container `localhost` is the container itself:

| Hop | Compose address | Why not `localhost` |
|---|---|---|
| backend → AI Engine | `http://ai-engine:8000` | DNS name of the `ai-engine` service on the Compose network |
| AI Engine → Ollama | `http://host.docker.internal:11434` | Ollama is on the host, not in the network |
| AI Engine → itself | `http://127.0.0.1:8000` | Only the container's own healthcheck uses this |

See the Compose section below for the full local workflow.

---

## 2. Versions

### Node.js — 22

| Item | Value |
|---|---|
| Tested | **Node 22** (22.23.2 verified: build, lint, 455 unit tests, 5 E2E tests) |
| CI | `actions/setup-node` with `node-version: '22'` |
| npm | 10.9.8 verified |
| `engines.node` in `package.json` | **not declared** |
| `.nvmrc` / `.node-version` | **absent** |

There is no version-pinning file. The value above reflects what was actually
exercised, not a declared constraint.

> **Known skew:** `apps/api` depends on `@types/node ^24`, which implies Node 24.
> Node 22 is what the full suite has been verified on, and it is what CI pins.
> The skew is unresolved; if the project standardises on Node 24, both the CI
> workflow and this document need updating together.

Why the invocation matters: this repository compiles TypeScript as ESM, and
NestJS 12 ships ESM-only packages. Jest must run with
`--experimental-vm-modules`. The `npm` scripts in `package.json` already include
it — calling `npx jest` directly fails. See
[troubleshooting](troubleshooting.md).

### Python — 3.11 or later

| Item | Value |
|---|---|
| Documented minimum | **3.11+** (AI Engine README) |
| Verified locally | 3.13.14 |
| `pyproject.toml` / `requires-python` | **absent** — the minimum is documentation only |
| `.python-version` | **absent** |

The AI Engine uses `sys.stdlib_module_names` and `X \| None` union syntax, both
of which need 3.10+ / 3.11+. 3.11 is the safe floor.

---

## 3. Backend variables (`apps/api`)

All are read at module initialisation.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | Port the NestJS server binds |
| `AI_ENGINE_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the AI Engine. Use a bare origin, with no trailing slash |
| `AI_ENGINE_TIMEOUT_MS` | `60000` | Milliseconds to wait for one AI Engine call |

### On `AI_ENGINE_TIMEOUT_MS`

The default is 60000, not 10000, because a real `llama3` analysis was measured
at **34.3 seconds**. A 10s default could not have completed against a live
model. 60000 also matches the AI Engine's own `REQUEST_TIMEOUT` budget of 60
seconds, so the backend's limit is an honest upper bound on the round trip
rather than an arbitrary number.

An AI Engine `504` and a local timeout both surface to callers as
`504 Gateway Timeout`, so crossing this boundary is behaviourally consistent.

> **Validation gap:** the value is parsed with `Number(...)` and is not checked.
> A non-numeric value such as `AI_ENGINE_TIMEOUT_MS=abc` becomes `NaN`, and
> `setTimeout` treats `NaN` as "fire immediately" — turning a typo into instant
> timeouts with no warning. Set a plain integer.

### Safe example

```bash
# apps/api
export PORT=3000
export AI_ENGINE_BASE_URL=http://127.0.0.1:8000
export AI_ENGINE_TIMEOUT_MS=60000
```

---

## 4. AI Engine variables (`apps/ai-engine`)

`apps/ai-engine` is present on this branch. It was imported from
`origin/feature/member3-ai` at `1c73b34` and is owned by Member 3; do not edit
it to work around a provider problem.

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `PROVIDER` | `ollama` | Provider selection. `ollama` is the verified value |
| `MODEL` | `llama3` | Model name forwarded to the provider |
| `PROVIDER_BASE_URL` | `http://localhost:11434` | Provider base URL |
| `REQUEST_TIMEOUT` | `60` | Seconds to wait for the provider |
| `PROVIDER_API_KEY` | unset | **Cloud providers only.** Do not set for Ollama |

> **`HOST` and `PORT` are inert inside the container.** The image's `CMD` is
> `uvicorn app.main:app --host 0.0.0.0 --port 8000`, so those two CLI flags win
> and the variables are ignored. Passing `-e HOST=... -e PORT=...` has no
> effect. Change the port via the Dockerfile `CMD` or a Compose override, not
> via these variables.

### Safe example (Ollama, no credentials)

```bash
export HOST=0.0.0.0
export PORT=8000
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
export REQUEST_TIMEOUT=60
# PROVIDER_API_KEY is intentionally unset — not used with Ollama
```

### If a cloud provider is ever used

Set `PROVIDER` to the provider name and export `PROVIDER_API_KEY` from your
shell or a secret manager. **Never** write the key into a committed file, a
`.env` that is tracked, or a command that lands in shell history.

### Model choice: `llama3`, and the `qwen3:8b` limitation

`llama3` is the model verified end-to-end. Confirm it is present on the host:

```bash
ollama list        # must list llama3:latest
```

> **Known limitation — `qwen3:8b` live timeout (unfixed, owned by Member 3).**
> `qwen3:8b` is a *thinking* model. Its reasoning trace arrives in
> `message.thinking`, which `OllamaProvider.complete` discards, and the provider
> sends no generation cap, so with `stream: False` generation cannot finish
> inside the read timeout. A real request therefore burns the full
> `REQUEST_TIMEOUT` and returns `504 PROVIDER_TIMEOUT`.
>
> This is acknowledged in `apps/ai-engine/tests/integration/test_failure_states.py`
> and `tests/integration/__init__.py` as a provider-architecture defect that is
> deliberately not worked around. **Use `llama3` for local validation.**
> It is recorded here so nobody re-diagnoses it as a networking or Compose fault.

---

## 5. `.env` handling

The repository `.gitignore` contains:

```
.env
.env.*
!.env.example
```

So real `.env` files are ignored, while `.env.example` templates are
committable. No `.env` file is tracked in this repository.

A root `.env.example` now exists for the Compose workflow. It documents the
host-port overrides and the model name only, contains no credential, and is
**optional** — every value in it has a working default in `compose.yaml`, so
`docker compose up --build` succeeds with no `.env` at all.

> **Known issue, AI Engine only:** the AI Engine does **not** load `.env` files.
> `python-dotenv` is absent from `requirements.txt` and `config.py` uses bare
> `os.getenv` with no `load_dotenv()` call. Copying `.env.example` to `.env` has
> **no effect** on the AI Engine — the documented step silently does nothing.
> Environment variables must be exported by the shell, or injected by Compose,
> until this is fixed.
>
> Note the asymmetry: Docker Compose *does* read a root `.env` for its own
> variable substitution, so the file is meaningful to Compose while remaining
> invisible to the AI Engine process.
>
> The backend has no `.env` loading either; it reads `process.env` directly.

---

## 6. Extension settings (`feature/member2-vscode-frontend`, separate branch)

Documented for completeness. **Not present on this branch and not verified
here** — read from that branch's `package.json` contribution points.

| Setting | Default | Notes |
|---|---|---|
| `aicode.backendUrl` | `http://localhost:3000` | Must match the backend's `PORT` |
| `aicode.useMockData` | `true` | When true, **no HTTP request is made at all** |
| `aicode.explanationMode` | `intermediate` | `brief` \| `intermediate` \| `advanced` |

Because mock mode defaults to `true`, the extension does not contact the backend
unless a user opts out.

> The extension's axios client uses a 30-second default timeout, which is
> **shorter** than the backend's measured ~34s. Real-mode analysis requests
> would currently abort client-side. Raising it is Member 2's task.

---

## 7. Docker Compose (recommended local workflow)

**Requires Docker Desktop** (or Docker Engine) with the daemon running, plus
Ollama **on the host** — Ollama is deliberately not containerised.

```bash
# 1. Ollama on the host, with the verified model
ollama serve
ollama list              # must list llama3:latest

# 2. Build and start backend + AI Engine
docker compose up --build

# 3. Confirm both are up and healthy
docker compose ps
docker compose logs --no-log-prefix ai-engine
docker compose logs --no-log-prefix api

# 4. Liveness (no AI Engine or Ollama dependency)
curl http://localhost:3002/health     # {"status":"ok"}
curl http://localhost:8002/health     # {"status":"ok"}

# 5. Real end-to-end analysis (this actually calls llama3 on the host)
curl -X POST http://localhost:3002/analysis/code \
  -H 'Content-Type: application/json' \
  -d '{"language":"python","code":"def add(a, b):\n    return a + b\n"}'
```

Shut down with `docker compose down`. The images are left in place.

### Host ports

The container ports are fixed by the service contract and are not configurable:
the backend listens on `3000` and dials `http://ai-engine:8000`; the AI Engine
listens on `8000`. Only the *host* side of the published mapping is adjustable,
so the stack does not collide with a development process already bound to
`3000` or `8000`.

| Service | Container port | Default host port | Override |
|---|---|---|---|
| `api` | `3000` | `3002` | `API_HOST_PORT` |
| `ai-engine` | `8000` | `8002` | `AI_ENGINE_HOST_PORT` |

Set them in a gitignored `.env` (`cp .env.example .env`) to claim `3000`/`8000`
when those are free.

### `host.docker.internal`

The `ai-engine` service reaches host Ollama through
`http://host.docker.internal:11434`, and `compose.yaml` maps that name
explicitly:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Docker Desktop provides this name implicitly; the explicit mapping is what makes
the same file work on Docker Engine for Linux. **Do not** replace it with
`localhost:11434` — inside the container that address is the container itself,
and every analysis request fails with `503 PROVIDER_UNAVAILABLE`.

### Readiness is configuration-only

`GET /ready` on the AI Engine performs **no LLM call**. It only checks that
`PROVIDER` is a non-empty string, so it returns `200 {"status":"ready"}` even
when Ollama is stopped, unreachable, or missing the model tag. The backend's
`GET /ready` proxies it and inherits the same weakness.

**A `200` from `/ready` is not proof that Ollama is working.** The Compose
healthchecks therefore use `/health` on both services. The only honest proof
that the LLM path works is a real analysis request.

### No Ollama service, no frontend container

`compose.yaml` defines exactly two services, `api` and `ai-engine`. There is
deliberately no service for Ollama, and none for the VS Code extension or
frontend.

---

## 8. Quick reference (no containers)

```bash
# 1. Ollama
ollama serve
ollama pull llama3

# 2. AI Engine
cd apps/ai-engine
pip install -r requirements.txt
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Backend
cd apps/api
npm ci
export AI_ENGINE_BASE_URL=http://127.0.0.1:8000
npm run start:dev

# 4. Verify
curl http://127.0.0.1:3000/health    # {"status":"ok"}   — no AI Engine needed
curl http://127.0.0.1:3000/ready     # 200 only if the AI Engine is ready
```

This path cannot be used while the Compose stack is running, because both
would try to bind `3000` and `8000`.
