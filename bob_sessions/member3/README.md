# Member 3 — IBM Bob evidence (PHASE 38)

**Date:** 2026-09-27
**Branch:** `feature/member3-ai-perf-regression-bob`
**IBM Bob version:** `1.126.0+bob2.2.0` (commit `30bf4b86252bd3410c41ce4a19e9496b499a6911`, x64)

## Summary

IBM Bob **is installed, running, authenticated, and has this repository open**.
The task requested for this phase — analysing the AI Engine → Ollama timeout
using the actual repository — was carried out, and its result is in
[`task07-ai-bob-timeout-analysis.md`](./task07-ai-bob-timeout-analysis.md).

However, **Bob's chat output cannot be captured programmatically from this
environment.** Every attempt made is recorded verbatim in
[`bob-cli-attempts.txt`](./bob-cli-attempts.txt). No screenshot was taken and no
chat transcript was exported, because no mechanism to do so exists here.

**Bob execution unavailable for transcript/screenshot capture; no fabricated
evidence created.**

## What is real and included

| File | What it is |
| --- | --- |
| `bob-version.txt` | Real `bobide --version` output. |
| `bob-cli-attempts.txt` | Verbatim transcript of the real CLI invocations and their real output, including the four failed capture attempts. |
| `agent-host-lock.json` | Bob's real agent-host lockfile, copied unmodified. |
| `agent-host-supervisor.txt` | Bob's real agent-host supervisor log, copied unmodified. Only the extension was changed from Bob's own `.log`, because this repository's `.gitignore` excludes `*.log` and force-adding it would fight that convention. Line 1 of the log records its real source path, `C:\Users\yashw\.bobide-server\cli\agent-host-stable.log`. |
| `agenthost-protocol-handshake.jsonl` | Bob's real agent-host-protocol event log, copied unmodified. |
| `task07-ai-bob-timeout-analysis.md` | The analysis itself, with line citations into this repository's real source. |
| `task05-ai-performance.md` | Pointer to the PHASE 35 performance report. |
| `task06-ai-regression.md` | Pointer to the PHASE 36 regression results. |

The four Bob state files are copied unmodified from Bob's own directories;
`bob-version.txt` and `bob-cli-attempts.txt` are transcripts of output that was
actually observed. The three `task*.md` files are written by hand, and the `task07`
claims in them cite this repository's real source. Nothing here is
reconstructed, illustrated, or invented.

> `agent-host-supervisor.txt` has trailing whitespace on six lines, so
> `git diff --check` reports it. **That whitespace is evidence, not sloppiness.**
> Those lines are Bob logging `[1.126.0 stdout]: ` followed by nothing, which is
> the record of the `bobide chat` invocations returning empty output. Stripping
> the spaces would erase the very fact the file is cited for. Please do not
> reformat it.

## Environment verification (real observations)

```
$ bobide --version
1.126.0+bob2.2.0
30bf4b86252bd3410c41ce4a19e9496b499a6911
x64
```

- Bob is running: 14–15 `IBM Bob.exe` processes during this phase.
- The workspace window is open on this repository. Real observed window title:
  `Welcome - AI-Code-Understanding-Assistant - IBM Bob`
- Bob is authenticated against IBM's backend. A real auth token entry exists in
  Bob's own state store at
  `%APPDATA%\IBM Bob\User\globalStorage\state.vscdb` under the key
  `secret://{"extensionId":"ibm.bob-code","key":"bob.auth.tokens-https://api.us-east.bob.ibm.com"}`.
- The CLI data directory is `C:\Users\yashw\.bobide`, the server data directory
  is `C:\Users\yashw\.bobide-server`.

## Why the transcript could not be captured

Four invocation modes were tried, with and without the window foregrounded. All
four returned exit code `0` with completely empty stdout and stderr, and none
created an agent-host session:

1. `bobide chat -m agent --new-window "<prompt>"`
2. `bobide chat -m ask --reuse-window "<prompt>"` (window not foregrounded)
3. `bobide chat -m ask --reuse-window "<prompt>"` (window foregrounded via
   `SetForegroundWindow`)
4. `bobide chat -m agent --reuse-window --add-file ... "<prompt>"`
   (window foregrounded)

Three further capture routes were investigated and ruled out on evidence:

- **`bobide agent logs`** streams live session events, but requires a session
  URI (`e.g. copilot:/<uuid>`) that only a live GUI session produces. No session
  was ever created, so there is no URI to stream.
- **The agent host HTTP API on `127.0.0.1:8731`.** The port is open and accepts
  TCP connections, but it is not an HTTP server. Plain `GET` requests to `/`,
  `/health`, `/api`, `/v1/sessions`, `/sessions` and `/openapi.json` all hang
  until the client timeout. Bob's own event log shows why:
  `"transport":"websocket"` — the agent-host protocol is JSON-RPC 2.0 over
  WebSocket.
- **A direct WebSocket client.** No WebSocket library is available
  (`websockets` and `websocket-client` are both absent), and installing one
  would modify the project's environment for no other purpose. The protocol's
  method names are not exposed by the CLI; only `initialize` and `listSessions`
  appear in the captured handshake.

**Screenshots.** The tool set available in this environment has no
screen-capture or OS-automation capability. A `bob_sessions/member3/*.png` cannot
be produced here without fabricating it, so none was created.

## Recommended follow-up (needs a machine with a desktop session)

`bobide chat` drives the GUI, so on an interactive desktop the capture is simply
a screenshot of the chat panel. For unattended capture, the two viable routes
are:

1. `bobide agent host` + a WebSocket JSON-RPC client, using the session URI
   surfaced by `bobide agent ps` while a GUI session is live.
2. `bobide serve-web` to serve the Bob UI over HTTP, so the session can be
   driven and captured headlessly.
