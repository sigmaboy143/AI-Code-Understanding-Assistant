# IBM Bob Usage Status — Phases 39 & 40

**Outcome: Phase 39 and Phase 40 were not completed. No Bob evidence and no screenshots were
produced, because IBM Bob could not be driven from the working session.**

This file records the environment investigation so the gap is traceable. It is deliberately **not**
placed under `bob_sessions/` and contains no Bob output, because no genuine Bob session was run.

> **Bob evidence unavailable; no fabricated screenshots created.**

## What was found

IBM Bob **is installed and running** on this machine. The blocker is not absence — it is the
absence of a *programmatic interface* to it from this session.

| Check | Result |
|---|---|
| Bob desktop app installed | Yes — `C:\Users\yashw\AppData\Local\Programs\IBM Bob\IBM Bob.exe` |
| Bob process running | Yes — 15 `IBM Bob` processes (renderer / utility / gpu-process) |
| Bob CLI binaries present | Yes — `bin\bobide`, `bin\bobide.cmd`, `bin\bobide-tunnel.exe` |
| Repo configured for Bob | Yes — `.bob/rules-ask/AGENTS.md`, `.bob/rules-agent/AGENTS.md`, `.bob/rules-plan/AGENTS.md` |
| Bob agent-host tunnel | `bobide-tunnel.exe agent host --host 127.0.0.1 --port 8731` — **port 8731 not listening** (connection refused) |
| Bob local HTTP port 23417 | **Not serving** — `GET /` timed out |
| Bob tool / MCP server in this session | **None** |

## Why no Bob session could be run

1. **No Bob tool is bound to this session.** The complete callable tool catalogue is 48 tools across
   exactly two namespaces — `tools.browser` (45) and `tools.opencode` (3). A search of that
   catalogue for any Bob-related tool returns zero results. There is no MCP server exposing Bob, and
   `opencode.json` is absent from both the user config and the repository, so no MCP server is
   configured for this project.
2. **Bob exposes no reachable network API.** Its only local listener associated with an IBM Bob
   process (port 23417) does not answer HTTP, and the agent-host tunnel on port 8731 is not
   listening. There is no endpoint to POST a prompt to or read a completion from.
3. **Bob is a desktop GUI application.** It is a VS Code–derived Electron app; interaction is
   through its window. This session has no desktop-automation or UI-driving capability.
4. **The browser tooling cannot substitute.** The available `browser` tools drive a web browser, not
   the Bob IDE, and they are additionally disconnected for this session
   (`No desktop browser is connected to this session`). Even connected, they would not have
   produced a genuine Bob session.

## What this means for the phases

| Phase | Status | Reason |
|---|---|---|
| **39 — Use Bob meaningfully** | **Not completed** | No way to submit a task to Bob or retrieve its output. Performing the AI-provider investigation without Bob would be *my own* analysis, not Bob evidence, and labelling it as Bob output would be fabrication. |
| **40 — Bob session screenshots** | **Not completed** | Screenshots must come from real Bob sessions. There were none, so `bob_sessions/member3/` was **not created**. No placeholder PNGs were written. |

The Phase 39 candidate tasks (provider timeout investigation, regression/test-coverage analysis,
troubleshooting analysis) all remain genuinely available and worth running once Bob is reachable. The
repository work they depend on is already understood from the bug log in
[`docs/ai-bugs/`](ai-bugs/README.md), which was produced directly from the code and a live Ollama
instance.

## To unblock

Any one of the following would make Phases 39 and 40 achievable:

- Register Bob as an MCP server for this project so a Bob tool appears in the session catalogue.
- Start the Bob agent-host tunnel so port 8731 accepts connections and expose a documented
  request/response API for prompts.
- Run the session in an environment where the Bob desktop UI can be driven or screenshotted
  directly, with the `browser`/desktop tooling connected.

## Related

- [`docs/ai-bugs/README.md`](ai-bugs/README.md) — five real, reproduced AI/integration defects
  recorded during this batch (Phase 44), including the known Phase 13 timeout blocker.
