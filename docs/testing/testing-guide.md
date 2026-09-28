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

These are **not present in this checkout**. The extension lives on
`feature/member2-vscode-frontend` (head `dc4941c`), where its `package.json` is
at the repository root.

| Purpose | Command | Notes |
|---|---|---|
| Extension unit | `npm run test:unit` | Mocha over compiled `out/test/unit`. Headless. Requires `npm run compile` first |
| Extension integration | `npm test` | Runs `vscode-test`; `pretest` runs `compile && lint`. **Not executed** — downloads and launches VS Code |
| Webview | — | **No test script and no lint script exist.** Only `npm run build` (`tsc && vite build`) |

`npm test` downloads a VS Code build and opens Electron. On Linux CI it needs
`xvfb-run`. `test:unit` is the headless alternative and is the better CI gate.

**What was actually run** against branch `dc4941c`, in an isolated worktree:
`npm ci` (root and `webview-ui`), `npm run lint` (exit 0), `npm run compile`
(exit 0), `npm run test:unit` (**42 passing**), and the webview `npm run build`
(exit 0). Its unmodified HTTP client and analysis adapter were then driven
against a live Compose backend + AI Engine + Ollama stack, with **15/15**
assertions passing. The GUI integration suite remains unrun.

---

## 5. What is not covered

| Gap | Detail |
|---|---|
| No automated multi-service E2E in CI | The real chain extension → backend → AI Engine → Ollama **has been run manually** and passes, but nothing asserts it on every commit |
| Full extension GUI suite not run | `npm test` (`vscode-test`) was not executed; headless equivalents all passed |
| No live-provider test in the AI Engine suite | `python -m pytest` never exercises a real model; live checks are manual |
| No CI for the AI Engine | `python -m pytest` is not run in any workflow |
| No CI for the extension | The Member 2 branch has no workflow |
| No AI quality evaluation | No dataset, no scoring, no regression baseline for answer quality |
| No contract test between services | Request/response shapes are enforced by TypeScript types only, not asserted at runtime |
| No coverage thresholds | `test:cov` exists but nothing enforces a minimum |

---

## 6. Running the full local check

```bash
cd apps/api
npm run lint
npm test
npm run test:e2e
npm run build
```

This is exactly the sequence CI runs in
`.github/workflows/backend.yml`, and it should pass with no external service
running.
