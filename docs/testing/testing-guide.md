# Testing Guide

Every test command in the project, and — more importantly — which tests are
deterministic and which need live services.

---

## 1. Summary

| Suite | Command | Working directory | Needs external services? |
|---|---|---|---|
| Backend unit + integration | `npm test` | `apps/api` | **No** |
| Backend E2E smoke | `npm run test:e2e` | `apps/api` | **No** |
| Backend lint | `npm run lint` | `apps/api` | **No** |
| Backend build | `npm run build` | `apps/api` | **No** |
| AI Engine unit | `python -m pytest` | `apps/ai-engine` | **No** — mock provider |
| AI Engine lint | *none exists* | — | — |
| Extension unit | `npm run test:unit` | repo root, on the Member 2 branch | **No** |
| Extension integration | `npm test` | repo root, on the Member 2 branch | Downloads VS Code |

Verified counts on the current branch:

| Suite | Suites / files | Tests | Result |
|---|---|---|---|
| `npm test` | 19 suites | 455 | all pass |
| `npm run test:e2e` | 1 suite | 5 | all pass |
| `npm run lint` | — | — | 0 warnings, 0 errors |
| `npm run build` | — | — | exit 0 |
| `python -m pytest` (AI Engine) | 29 files | 870 | all pass, 1 unrelated `anyio` deprecation warning |

---

## 2. Backend tests

```bash
cd apps/api
npm ci          # first time only
```

### 2.1 Unit and integration tests

```bash
npm test
```

Runs Jest across `src/**/*.spec.ts`. 19 suites, 455 tests. **Fully
deterministic** — no network, no AI Engine, no database. AI Engine interaction
is exercised with a mocked `fetch`.

Coverage includes:

- DTO validation boundaries, including the exact 100000-character limit and the
  100001 rejection
- The AI Engine client's URL, method, headers, body, success path, every
  documented error status, network failure, and timeout
- The adapter's request mapping, response mapping, confidence normalisation,
  evidence mapping, and error translation
- The allowlist redactor, including CR/LF forging, header injection, URL
  credential stripping, and immutability
- Correlation ID generation, validation, echo, and concurrency isolation
- `GET /health` and `GET /ready` behaviour

### 2.2 E2E smoke tests

```bash
npm run test:e2e
```

Uses a separate config, `test/jest-e2e.json`. 1 suite, 5 tests. Boots the real
`AppModule` and drives it over HTTP with supertest, so the assembled graph —
including the global `APP_PIPE` and correlation middleware — is genuinely
exercised.

| Test | Asserts |
|---|---|
| `GET /health` returns 200 and `{ "status": "ok" }` | Liveness contract |
| `GET /health` answers without contacting the AI Engine | No hidden I/O |
| `GET /health` echoes a correlation ID | Middleware is wired |
| A supplied `X-Request-Id` is honoured | ID propagation |
| `POST /analysis/code` with an unknown property returns 400 | Global pipe is applied |

**Fully deterministic.** `GET /health` performs no I/O by design, and the
validation test is rejected by `forbidNonWhitelisted` on the payload's own
merits, so it can never reach the AI Engine. This has been verified by re-running
the suite with `AI_ENGINE_BASE_URL` pointed at a dead port — still 5/5.

`GET /ready` is deliberately **not** covered here, because it probes the AI
Engine and its result would depend on machine state. Its failure mapping is
covered deterministically in `src/health/health.service.spec.ts`.

### 2.3 Lint

```bash
npm run lint
```

`oxlint --type-aware` over `src/` and `test/`. Expected: 0 warnings, 0 errors.
Type-aware linting needs a platform binary from `oxlint-tsgolint`, which
resolves automatically for Linux, macOS, and Windows via optional dependencies.

### 2.4 Build

```bash
npm run build
```

`nest build` via `tsc`. `tsconfig.build.json` excludes `test/`, so specs are not
compiled into `dist/`.

### 2.5 Never call bare `npx jest`

This repository compiles TypeScript as ESM, and the `test` and `test:e2e`
scripts carry `--experimental-vm-modules`. Running `npx jest` directly skips
that flag and fails on NestJS's ESM-only packages **before any test runs**, with
a misleading "Must use import to load ES Module" error. Always use the npm
scripts.

---

## 3. AI Engine tests

```bash
cd apps/ai-engine
pip install -r requirements.txt
python -m pytest
```

`pytest.ini` sets `testpaths = tests` and `asyncio_mode = auto`, so bare
`pytest` also works. The README documents `python -m pytest tests/ -q`.

29 test files, 870 tests. **Deterministic** — a mock LLM provider is used, so no
Ollama and no network access is required.

Covered: API contract and error envelope, health, orchestrator, schemas,
evidence, context builder, retrieval, reasoning, output validation, and each
analysis agent.

**No linter or type checker is configured.** There is no `ruff`, `flake8`,
`mypy`, `tox`, or `pre-commit` configuration in the AI Engine tree. A
`ruff check` string appears in the codebase only as test fixture data for the
parser, not as tooling.

---

## 4. Extension and webview tests

The extension lives at the **repository root** in this checkout, with its
`package.json` there (it was merged from `feature/member2-vscode-frontend`,
head `dc4941c`).

| Purpose | Command | Notes |
|---|---|---|
| Extension unit | `npm run test:unit` | Mocha over compiled `out/test/unit`. Headless. Requires `npm run compile` first. 42 tests |
| Extension integration | `npm test` | Runs `vscode-test` in a real Extension Development Host; `pretest` runs `compile && lint`. 67 tests, no Ollama or backend required |
| Webview | — | **No test script and no lint script exist.** Only `npm run build` (`tsc && vite build`) |

`npm test` opens Electron. On Linux CI it needs `xvfb-run`. `test:unit` is the
headless alternative and is the better CI gate.

The integration suite deliberately does **not** stub the `vscode` module: a
stub would test the stub. It runs the real activation path and asserts what VS
Code actually loaded (every command in `package.json` is registered, the
`main` entry point exists, the activity-bar view is a webview), that the panel
serves the built `webview-ui/dist/assets/index.js` under a nonce'd CSP, and
that the built React app posts its `ready` message. Real mode is then driven
against a local `node:http` server that returns a genuine `AnalysisResult`, so
the axios call, the `X-Request-Id` header, the response mapping, the
capability-notice path and the error paths are all covered without Ollama.

---

## 5. What is not covered

| Gap | Detail |
|---|---|
| No automated multi-service E2E in CI | The real chain extension → backend → AI Engine → Ollama **has been run manually** and passes, but nothing asserts it on every commit. `npm test` covers everything up to and including the backend's HTTP contract, against a local stub server |
| No live-provider test in the AI Engine suite | `python -m pytest` never exercises a real model; live checks are manual |
| No CI for the AI Engine | `python -m pytest` is not run in any workflow |
| No CI for the extension | The Member 2 branch has no workflow |
| No AI quality evaluation | No dataset, no scoring, no regression baseline for answer quality |
| No contract test between the backend and the AI Engine | The extension → backend request and response shapes **are** asserted at runtime by `src/test/panel.test.ts`, but the backend → AI Engine hop is enforced by TypeScript types only |
| No coverage thresholds | `test:cov` exists but nothing enforces a minimum |
| No webview test suite | The React app has no tests; it is only type-checked and built, and the built bundle is asserted to load by the extension-host suite |

---

## 6. Running the full local check

Backend and AI Engine — exactly the sequence CI runs in
`.github/workflows/backend.yml`:

```bash
cd apps/api
npm run lint
npm test
npm run test:e2e
npm run build
```

Extension:

```bash
npm run lint
npm run build-webview
npm run test:unit
npm test
```

Both should pass with no external service running.
