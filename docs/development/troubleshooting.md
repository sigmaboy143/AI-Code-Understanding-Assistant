# Troubleshooting

Problems that have actually been encountered in this project, with their causes
and fixes. Nothing here is speculative.

---

## 1. Backend

### 1.1 `Must use import to load ES Module`

**Symptom**

```
Test suite failed to run
Must use import to load ES Module:
  .../node_modules/@nestjs/common/index.js
The file contains ESM syntax (import/export) that could not be executed as CommonJS.
```

**Cause**

This project compiles TypeScript with `module: nodenext`, and NestJS 12 ships
ESM-only packages. Jest must run with `--experimental-vm-modules`. The `test`
and `test:e2e` scripts in `package.json` already set that flag.

**Fix**

Use the npm scripts, never `npx jest`:

```bash
npm test                              # correct
npm run test:e2e                      # correct
npx jest                              # WRONG — omits the flag
```

**If it still fails,** check the working directory. Both scripts use relative
paths (`./node_modules/jest/bin/jest.js`, `./test/jest-e2e.json`) and must run
from `apps/api`.

### 1.2 E2E suite fails to run while unit tests pass

**Symptom**

`npm test` passes but `npm run test:e2e` fails at the first import, naming
`@nestjs/testing`.

**Cause**

`test/jest-e2e.json` was originally the stock `nest new` scaffold, which lacks
the ESM settings that `jest.config.ts` has.

**Fix**

`test/jest-e2e.json` must contain all three:

```json
{
  "extensionsToTreatAsEsm": [".ts"],
  "transform": {
    "^.+\\.(t|j)s$": ["ts-jest", { "useESM": true, "tsconfig": { "module": "ESNext", "moduleResolution": "bundler" } }]
  },
  "moduleNameMapper": { "^(\\.{1,2}/.*)\\.js$": "$1" }
}
```

This is already applied. If the two Jest configs are ever changed, change both.

### 1.3 `lint` fails on a clean checkout

**Symptom**

`oxlint --type-aware` reports a missing or broken binary.

**Cause**

Type-aware linting needs a platform binary from `oxlint-tsgolint`, which ships
as optional dependencies per platform.

**Fix**

Run a full `npm ci` rather than `npm install`. It resolves the correct binary
for Linux, macOS, or Windows. A partial or hoisted install can miss it.

### 1.4 Analysis returns `504 Gateway Timeout`

**Symptom**

`POST /analysis/code` returns 504.

**Cause**

Either the backend's 60-second budget elapsed, or the AI Engine returned
`PROVIDER_TIMEOUT`.

**Fix**

Check how long the model actually takes. A real `llama3` analysis was measured
at **34.3 seconds**, so anything close to 60s is genuinely slow rather than
broken.

- Confirm the model is loaded: `ollama ps`
- If inference is this slow, a smaller model or GPU offload will help
- Raise `AI_ENGINE_TIMEOUT_MS` if the model legitimately needs longer
- Remember clients need an even larger budget — the extension currently uses 30s

### 1.5 Every request fails immediately

**Symptom**

Requests fail almost instantly rather than after a delay.

**Cause**

`AI_ENGINE_TIMEOUT_MS` is not a valid integer, so `Number(...)` returns `NaN`,
and `setTimeout` treats `NaN` as "fire immediately".

**Fix**

```bash
echo $AI_ENGINE_TIMEOUT_MS     # must be a plain integer
export AI_ENGINE_TIMEOUT_MS=60000
```

There is no validation of this value, so a typo produces this symptom silently.

### 1.6 `404` from `/auth`, `/users`, `/projects`, and similar

**Symptom**

Any of these returns 404.

**Cause**

Not a bug. Those modules declare a controller with **zero route handlers**. The
controller files are 207–261 bytes — class declarations only. They exist to fix
the module graph, not to serve traffic.

Implemented routes: `/`, `/health`, `/ready`, `/analysis/code`,
`/analysis/file`, `/explanations`, `/files/:id/analysis`, `/symbols`,
`/relationships`.

### 1.7 `/symbols` or `/relationships` returns `[]`

**Symptom**

`200` with an empty array.

**Cause**

Not a bug. Both services return `Promise.resolve([])`. The routes and models
are real; extraction and resolution are not implemented. They do not call the
AI Engine.

### 1.8 Port 3000 already in use

**Fix**

```bash
export PORT=3001
```

Then point the client at the new port. Note that `aicode.backendUrl` on the
extension branch defaults to `http://localhost:3000`.

---

## 2. AI Engine

### 2.1 Copying `.env.example` to `.env` does nothing

**Symptom**

`cp .env.example .env`, restart, and the AI Engine still uses defaults.

**Cause**

**Known bug.** The AI Engine does not load `.env` files at all.
`python-dotenv` is absent from `requirements.txt`, and `config.py` uses bare
`os.getenv` with no `load_dotenv()` call.

**Fix, for now**

Export the variables explicitly:

```bash
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
```

A permanent fix requires adding `python-dotenv` and calling `load_dotenv()` in
the config module. That is Member 3's change to make.

### 2.2 `GET /ready` returns 503

**Cause**

`/ready` verifies **configuration only** — that a provider name is set and, for
cloud providers, that an API key exists. It makes no LLM call. It returns 503
when `PROVIDER` is unset.

**Fix**

```bash
export PROVIDER=ollama
```

### 2.3 `GET /ready` returns 200 but analysis still fails

**Symptom**

Readiness says ready, but `POST /api/v1/code-understanding` fails.

**Cause**

**Expected behaviour, not a bug.** The AI Engine's readiness check never
contacts the provider. It cannot detect that Ollama is stopped or the model is
missing. The backend's `/ready` inherits this.

**Fix**

Test the provider directly:

```bash
curl http://localhost:11434/api/tags        # is Ollama up?
ollama list                                 # is the model pulled?
```

### 2.4 Ollama model not found

**Symptom**

`404` or a model-not-found error from the provider.

**Fix**

```bash
ollama pull llama3
ollama list
```

`MODEL` must match the pulled name exactly.

### 2.5 Port 8000 already in use

**Fix**

```bash
export PORT=8001
```

Then update the backend to match:

```bash
export AI_ENGINE_BASE_URL=http://127.0.0.1:8001
```

### 2.6 `ModuleNotFoundError: No module named 'app'`

**Cause**

The AI Engine imports as `from app.config import ...`, so `apps/ai-engine` must
be the working directory. Running uvicorn from the repository root breaks it.

**Fix**

```bash
cd apps/ai-engine
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The same applies to pytest — `pytest.ini` and the `tests/` package are relative
to `apps/ai-engine`.

---

## 3. Integration

### 3.1 Backend `/ready` returns 503 while the AI Engine's `/ready` returns 200

**Cause**

Different hosts or ports. The backend defaults to `http://127.0.0.1:8000`.

**Fix**

```bash
echo $AI_ENGINE_BASE_URL
curl "$AI_ENGINE_BASE_URL/ready"
```

If that works, restart the backend — `AI_ENGINE_BASE_URL` is read once at module
initialisation, so changing it afterwards has no effect without a restart.

### 3.2 Analysis succeeds but the client reports a timeout

**Symptom**

The backend returns `201`, but the caller reports a timeout.

**Cause**

Client-side timeout shorter than real inference. A real `llama3` analysis took
**34.3 seconds**; the extension's axios client defaults to **30 000 ms**.

**Fix**

Raise the **client's** timeout above the backend's latency budget. This is a
Member 2 change. The backend's own default is already 60s.

### 3.3 Correlation ID does not match

**Symptom**

The `X-Request-Id` you sent is not the one you got back.

**Cause**

Your ID did not match `/^[A-Za-z0-9._~-]{1,128}$/`, so it was replaced with a
fresh UUID. The replacement is used consistently in the header, the response
body, and the logs.

**Fix**

Use only letters, digits, `.`, `_`, `~`, and `-`, up to 128 characters. CR and
LF are rejected on purpose, to prevent header injection and log forging.

### 3.4 `npm audit` reports high-severity advisories

**Symptom**

5 vulnerabilities: 2 low, 1 moderate, 2 high.

**Cause**

All five are in **`@nestjs/mau`**, a **devDependency** used only by the deploy
CLI. Its `undici` and `tmp` dependencies carry the advisories. It is not loaded
during build, test, lint, or request serving.

**Fix**

Confirm the production surface is clean:

```bash
npm audit --omit=dev --audit-level=high
# found 0 vulnerabilities
```

The offered fix is `npm audit fix --force`, which installs `@nestjs/mau@0.0.6` —
a breaking change to a deploy-only tool. It has deliberately not been applied.
