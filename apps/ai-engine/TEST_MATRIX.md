# AI Engine Test Matrix

Every row below is backed by tests that exist in `apps/ai-engine/tests/` today.
Nothing is inferred from implementation alone, and no row is marked PASS on the
strength of code that is only *present* — a row is PASS only when a test that
exercises the behaviour actually ran and passed.

## How these numbers were produced

```bash
cd apps/ai-engine
python -m pytest tests -q
```

- **Total collected:** 782 tests across 26 test files.
- **Result at the time of writing:** `782 passed, 1 warning` in ~11s.
- Python used: 3.13.7. The suite also runs on 3.11 (the `Dockerfile` floor) in CI.

Counts in the table are the collected test counts of the listed files, or the
count of the scenario-specific tests inside a shared file (noted inline).

## Deterministic vs live

**Every test in this repository is deterministic.** There is no live-provider
test in the suite. Provider behaviour is exercised by monkeypatching `httpx`
(transport, status codes, malformed bodies) or by injecting `MockProvider`.
This is enforced, not merely asserted: CI re-runs the whole suite with
`PROVIDER_BASE_URL=http://192.0.2.1:11434` (RFC 5737 TEST-NET-1, permanently
unroutable) and `MODEL=qwen3:8b`, and requires 782 passing.

The consequence is stated plainly: **the suite verifies the AI Engine's own
logic, contracts, and failure handling. It does not verify that a real LLM
produces a good answer.** That gap is the Phase 13 blocker in the last row.

## Matrix

| # | Scenario | Test file(s) | Tests | Result | Deterministic / Live | Known limitation / blocker |
|---|----------|--------------|-------|--------|----------------------|---------------------------|
| 1 | **explanation** — explains submitted code, answers the question, extracts flow steps, never fabricates repo facts | `tests/test_explanation_agent.py`; `tests/integration/test_e2e_user_scenarios.py` (4 `explanation_scenario` tests) | 34 + 4 | **PASS** | Deterministic (`MockProvider`) | Free-text path only. The `explanation` field of `CodeUnderstandingResponse` is schema-ready but never populated by the parser, so only `summary` is asserted. Flow steps use line-level heuristics, no AST. |
| 2 | **WHY / reasoning** — explains why a change was made from supplied Git context; prompt construction, anti-fabrication, question priority | `tests/test_git_reasoning_agent.py`; `tests/test_reasoning.py`; `tests/integration/test_e2e_user_scenarios.py` (6 `why_scenario` tests) | 37 + 28 + 6 | **PASS** | Deterministic | Git context must be supplied by the caller; the agent runs no Git commands and never scans the repository. `GitContext` has no history channel, so multi-commit reconstruction is untested and unimplemented. |
| 3 | **debugging** — locates the failure and infers root cause from error message, stack trace, source, chunks | `tests/test_debug_impact_agent.py` (27 `DebugAgent` tests); `tests/integration/test_e2e_user_scenarios.py` (4 `debug_scenario` tests) | 27 + 4 | **PASS** | Deterministic | Stack-trace parsing is Python-frame-specific; other languages' traceback formats are not covered. Code is never executed and errors are never reproduced. |
| 4 | **impact** — direct and one-hop transitive dependants, related tests, honest `UNKNOWN` when nothing is supplied | `tests/test_debug_impact_agent.py` (28 `ImpactAgent` tests); `tests/integration/test_e2e_user_scenarios.py` (3 `impact_scenario` tests) | 28 + 3 | **PASS** | Deterministic | No dependency parser. Only one transitive hop is explored; deeper chains are deliberately not analysed because supplied data may be incomplete. With empty `relationships`, affected lists are always empty. |
| 5 | **relationships** — retrieval finds the relevant chunk, ranking, dedup, budget trimming, verbatim attribution | `tests/test_retrieval.py`; `tests/test_context_builder.py`; `tests/integration/test_e2e_user_scenarios.py` (7 `relationship_scenario` tests) | 24 + 40 + 7 | **PASS** | Deterministic (pure-Python lexical) | Token-overlap scoring only — no stemming, TF-IDF, or BM25. Not production RAG. `extra_sections` is always empty. |
| 6 | **architecture** — components, entry points, dependency relationships, data flow, and honest `UNKNOWN` on empty context | `tests/test_architecture_agent.py` | 37 | **PASS** | Deterministic (library-level) | **Reflects only the supplied `ArchitectureContext` and nothing more.** The agent does not scan the repository, parse code, or infer undeclared dependencies. It is not exposed as its own HTTP capability, so all 37 tests are library-level, not API-level. |
| 7 | **evidence** — evidence items reference only supplied material, never fabricated, human-readable, 1-based lines | `tests/test_evidence.py`; `tests/integration/test_confidence_evidence_mapping.py`; `tests/evaluation/test_ai_output_quality.py` (evidence subset) | 55 + 19 | **PASS** | Deterministic | Claim-level evidence mapping is not implemented. `git_commit`, `test`, and `documentation` source types are never automatically populated. |
| 8 | **confidence** — free-text answers are always `UNKNOWN`; availability of code or chunks never upgrades it; vocabulary is exactly three states | `tests/integration/test_confidence_evidence_mapping.py`; `tests/evaluation/test_ai_output_quality.py`; `tests/test_output_validation.py` (confidence subset) | 19 + 44 | **PASS** | Deterministic | `UNKNOWN` is the *only* level the free-text pipeline can produce, so the passing tests prove non-overclaiming, not calibrated confidence. There is no numeric score. |
| 9 | **onboarding** — project overview, entry points, components, dev flow, sections with per-section confidence | `tests/test_onboarding_agent.py`; `tests/integration/test_e2e_user_scenarios.py` (4 `onboarding_scenario` tests) | 52 + 4 | **PASS** | Deterministic | **Reflects the current public surface:** the onboarding agent is deliberately *not* a separate API capability — its behaviour is asserted at library level, and the integration tests assert the question flows through the ordinary `POST /api/v1/code-understanding` endpoint. It does not scan the file system and cannot determine deployment process. |
| 10 | **provider failure** — connection refused, upstream 500/404, unreachable host, unavailable model all map to 502/503 without leaking the upstream address or error text | `tests/integration/test_provider_error_handling.py` (4); `tests/integration/test_failure_states.py` (8); `tests/test_api.py` (503/502 tests) | 4 + 8 + 2 | **PASS** | Deterministic (monkeypatched `httpx`) | Only Ollama is implemented. Cloud providers named in config (`openai`, `anthropic`) are guarded in `is_configured` but have no provider implementation and no tests. |
| 11 | **timeout handling** — `httpx` read timeout, `asyncio` timeout, and pool exhaustion all map to 504 `PROVIDER_TIMEOUT`; not misreported as connection errors; configured budget is not disclosed to the client | `tests/integration/test_provider_error_handling.py` (5); `tests/integration/test_failure_states.py` (4); `tests/test_api.py`; `tests/test_output_validation.py` | 5 + 4 + 1 + 1 | **PASS** | Deterministic (simulated timeouts) | **This row covers the timeout *handler* only.** It does not mean a real request completes. See row 13 — the real `qwen3:8b` full-analysis request still times out. |
| 12 | **malformed response** — missing `message`/`content` key, non-JSON body, JSON array, empty object, and empty/whitespace/oversized content all handled without crashing or leaking upstream content | `tests/integration/test_provider_error_handling.py` (5); `tests/integration/test_failure_states.py` (5); `tests/test_output_validation.py` | 5 + 5 + 50 | **PASS** | Deterministic | Malformed *upstream* bodies map to 502. Malformed *model* content falls back to `"No summary produced by provider."` rather than being parsed, because there is no structured-JSON extraction yet. |
| 13 | **live `qwen3:8b` full code-understanding analysis** | *(no test file — deliberately not automated)* | 0 | **FAIL / BLOCKED** | **Live** | **Phase 13 blocker, unresolved.** A real `qwen3:8b` full code-understanding request through Ollama exceeds the 120-second budget and times out. Not fixed in this batch. There is therefore **no automated end-to-end proof that a real model returns a usable answer** — only that the engine handles whatever the provider returns. |

## Cross-cutting contracts

Not in the requested category list, but part of what the suite actually proves.

| Scenario | Test file(s) | Tests | Result | Deterministic / Live |
|-----------|--------------|-------|--------|----------------------|
| Request schema / validation, 422 before any provider call | `tests/integration/test_request_contract.py`; `tests/test_schemas.py`; `tests/test_api.py` | 15 + 31 + 8 | **PASS** | Deterministic |
| Response contract, optional fields stay empty | `tests/integration/test_response_contract.py`; `tests/test_e2e_user_scenarios.py` (3 cross-scenario) | 25 + 3 | **PASS** | Deterministic |
| Health / readiness contract, no provider call, no secret disclosure | `tests/integration/test_health_contract.py`; `tests/test_health.py`; `tests/test_api.py` | 10 + 1 + 3 | **PASS** | Deterministic |
| Dependency grounding in structured output | `tests/test_dependency_grounding.py`; `tests/integration/test_dependency_grounding_api.py`; `tests/evaluation/test_ai_output_quality.py` (subset) | 7 + 21 | **PASS** | Deterministic |
| Orchestration pipeline end to end (mocked provider) | `tests/test_orchestrator.py`; `tests/test_output_validation.py` | 25 + 50 | **PASS** | Deterministic |
| Documentation agent (keyword matching) | `tests/test_documentation_agent.py` | 29 | **PASS** | Deterministic |

## Honest summary

- 12 of 12 requested categories have **real, passing, deterministic tests**.
- 1 category — **live `qwen3:8b` full analysis** — is **FAIL/BLOCKED** (Phase 13) and has **no automated test**, because it does not currently work.
- Rows 10–12 passing means the engine's *error handling* is correct. It does **not** mean the happy path works against a real model. That distinction is the whole point of keeping row 13 in this table instead of quietly dropping it.
