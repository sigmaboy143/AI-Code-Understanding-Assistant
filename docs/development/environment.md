# Environment

Ports, variables, and version requirements. No real credentials appear in this
document; every value below is either a default from source code or a safe
placeholder.

---

## 1. Ports

| Service | Port | Source |
|---|---|---|
| NestJS backend | `3000` | `main.ts`, `process.env.PORT ?? 3000` |
| FastAPI AI Engine | `8000` | AI Engine default, `feature/member3-ai` |
| Ollama | `11434` | AI Engine `PROVIDER_BASE_URL` default |

The backend reaches the AI Engine over HTTP on `127.0.0.1:8000` by default. The
AI Engine reaches Ollama on `localhost:11434`.

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

## 4. AI Engine variables (`apps/ai-engine`, separate branch)

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `PROVIDER` | `ollama` | Provider selection. `ollama` is the verified value |
| `MODEL` | `llama3` | Model name forwarded to the provider |
| `PROVIDER_BASE_URL` | `http://localhost:11434` | Provider base URL |
| `REQUEST_TIMEOUT` | `60` | Seconds to wait for the provider |
| `PROVIDER_API_KEY` | unset | **Cloud providers only.** Do not set for Ollama |

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

> **Known issue, AI Engine only:** the AI Engine does **not** load `.env` files.
> `python-dotenv` is absent from `requirements.txt` and `config.py` uses bare
> `os.getenv` with no `load_dotenv()` call. Copying `.env.example` to `.env` has
> **no effect** — the documented step silently does nothing. Environment
> variables must be exported by the shell until this is fixed.
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

## 7. Quick reference

```bash
# 1. Ollama
ollama serve
ollama pull llama3

# 2. AI Engine  (checkout of feature/member3-ai)
cd apps/ai-engine
pip install -r requirements.txt
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Backend  (this repository)
cd apps/api
npm ci
export AI_ENGINE_BASE_URL=http://127.0.0.1:8000
npm run start:dev

# 4. Verify
curl http://127.0.0.1:3000/health    # {"status":"ok"}   — no AI Engine needed
curl http://127.0.0.1:3000/ready     # 200 only if the AI Engine is ready
```
