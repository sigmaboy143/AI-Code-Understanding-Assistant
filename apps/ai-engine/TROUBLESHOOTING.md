# AI Engine — Troubleshooting

Symptom-driven fixes for the AI Engine (`apps/ai-engine`). Every entry uses the
same four headings so you can scan for the part you need:

- **Problem** — what you observe.
- **Cause** — why it happens, and whether it is a defect or a configuration mistake.
- **Check** — copy-pasteable commands that confirm or rule it out.
- **Fix** — the action that resolves it.

**Status labels** used below:

| Label | Meaning |
|---|---|
| **VERIFIED** | Confirmed against the code in this repository, or by a command that was actually run. |
| **LIMITATION** | A deliberate gap in the current implementation. Not your setup. |
| **BLOCKER** | A defect that has been diagnosed but is **not** fixed. |
| **NOT IMPLEMENTED** | Described for context only — no code exists for it. |

For configuration, deployment, and the test suite see
[`README.md`](README.md). The most common single cause of "it works locally but
not in Docker" is a `localhost` address inside the container — see
[section 15](#15-wrong-provider_base_url).

---

## Contents

| # | Symptom |
|---|---|
| [1](#1-the-ai-engine-fails-to-start) | The AI Engine fails to start |
| [2](#2-python-dependency-installation-fails) | Python dependency installation fails |
| [3](#3-missing-python-module-modulenotfounderror-or-importerror) | `ModuleNotFoundError` / `ImportError` |
| [4](#4-port-8000-is-already-in-use) | Port 8000 is already in use |
| [5](#5-the-health-endpoint-fails) | `GET /health` fails |
| [6](#6-the-readiness-endpoint-fails) | `GET /ready` fails |
| [7](#7-ollama-is-unavailable) | Ollama is unavailable |
| [8](#8-connection-refused-connecting-to-ollama) | Connection refused connecting to Ollama |
| [9](#9-model-unavailable) | Model unavailable |
| [10](#10-provider-timeout) | Provider timeout |
| [11](#11-malformed-provider-response) | Malformed provider response |
| [12](#12-invalid-input-or-http-422) | Invalid input / HTTP 422 |
| [13](#13-docker-build-failure) | Docker build failure |
| [14](#14-docker-container-startup-failure) | Docker container startup failure |
| [15](#15-wrong-provider_base_url) | Wrong `PROVIDER_BASE_URL` |
| [16](#16-missing-environment-variable) | Missing environment variable |
| [17](#17-env-is-ignored) | `.env` is ignored |
| [18](#18-qwen38b-full-analysis-timeout-blocker) | `qwen3:8b` full-analysis timeout (BLOCKER) |

---

## 1. The AI Engine fails to start

**Problem**

Uvicorn exits immediately. Typical output:

```text
ERROR:    [Errno 2] No such file or directory: 'uvicorn'
```

or, when the application package cannot be found:

```text
ERROR:    Error loading ASGI app. Could not import module "app.main".
```

**Cause**

One of:

- The process is not running inside the virtual environment, so `uvicorn` and
  `fastapi` are not importable.
- The working directory is not `apps/ai-engine`, so the `app` package cannot be
  imported (Uvicorn resolves `app.main:app` relative to the current directory).
- The wrong Python is on `PATH`.

**Check**

```bash
# bash / macOS / Linux
cd apps/ai-engine
which python
python --version
python -c "import fastapi, uvicorn; print('imports ok')"
python -c "import app.main; print('app ok')"
```

```powershell
# Windows PowerShell
cd apps\ai-engine
Get-Command python
python --version
python -c "import fastapi, uvicorn; print('imports ok')"
python -c "import app.main; print('app ok')"
```

**Fix**

Start the process from `apps/ai-engine`, inside the environment, using the
environment's own interpreter:

```bash
cd apps/ai-engine
source .venv/bin/activate          # macOS / Linux
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
cd apps\ai-engine
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If the import still fails, the dependencies are not installed — continue to
[section 2](#2-python-dependency-installation-fails).

---

## 2. Python dependency installation fails

**Problem**

```text
ERROR: Could not find a version that satisfies the requirement fastapi==0.115.5
ERROR: No matching distribution found for fastapi==0.115.5
```

or a resolver conflict such as:

```text
ERROR: Cannot install ... because these package versions have conflicting dependencies.
```

**Cause**

- `requirements.txt` pins exact versions (`fastapi==0.115.5`,
  `uvicorn[standard]==0.32.1`, `httpx==0.27.2`, `pytest==8.3.4`,
  `pytest-asyncio==0.24.0`). Any other package in the same environment that
  requires a different version of `fastapi`, `httpx`, or `pydantic` cannot be
  reconciled.
- A proxy or a restricted network blocks access to the package index.
- Installing into the system Python rather than a dedicated virtual environment.

**Check**

```bash
cd apps/ai-engine
python -m pip --version
python -m pip install -r requirements.txt
python -m pip check
python -m pip list
```

**Fix**

Install into a clean virtual environment (see [README Setup](README.md#setup)):

```bash
cd apps/ai-engine
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

```powershell
cd apps\ai-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the index is unreachable, configure your package proxy/index in `pip` or
`PIP_*` environment variables and retry. If a conflict is reported, the fix is
to remove the competing package from that environment — do not edit
`requirements.txt` to make a conflict disappear, because those pins are what
the test suite is verified against.

---

## 3. Missing Python module (ModuleNotFoundError or ImportError)

**Problem**

```text
ModuleNotFoundError: No module named 'app'
ModuleNotFoundError: No module named 'app.config'
ModuleNotFoundError: No module named 'httpx'
```

**Cause**

- `No module named 'app'` or `'app.config'`: the working directory is wrong, or
  `apps/ai-engine` is not on `sys.path`. The `app` package only exists under
  `apps/ai-engine/app/`.
- `No module named 'httpx'` / `'fastapi'` / `'uvicorn'`: dependencies are not
  installed in the interpreter running the process.
- Running pytest from the repository root without the `apps/ai-engine` layout
  being picked up, so the package is not importable.

**Check**

```bash
# bash / macOS / Linux
pwd
ls app/main.py
python -c "import app, app.config, app.main; print(app.__file__)"
```

```powershell
# Windows PowerShell
Get-Location
Test-Path app\main.py
python -c "import app, app.config, app.main; print(app.__file__)"
```

Confirm which interpreter is in use:

```bash
python -c "import sys; print(sys.executable)"
```

**Fix**

```bash
cd apps/ai-engine
python -m pytest tests -q            # run tests from apps/ai-engine
```

or, from the repository root (also verified to work):

```bash
python -m pytest apps/ai-engine/tests -q
```

If the interpreter is wrong, activate the environment
(`.venv`) or invoke it by full path
(`.\.venv\Scripts\python.exe`, `.venv/bin/python`). If a third-party module is
missing, see [section 2](#2-python-dependency-installation-fails).

---

## 4. Port 8000 is already in use

**Problem**

```text
ERROR:    [Errno 48] Address already in use
ERROR:    [Errno 98] address already in use
```

**Cause**

Another process — commonly a previous `uvicorn --reload` run, or a container
started earlier with `-p 8000:8000` — is already bound to port `8000`.

**Check**

macOS / Linux:

```bash
lsof -i :8000
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
netstat -ano | findstr :8000
```

Docker:

```bash
docker ps --filter "publish=8000"
```

**Fix**

Stop the other listener:

```bash
# macOS / Linux
kill <PID>
```

```powershell
# Windows PowerShell
Stop-Process -Id <PID> -Force
```

```bash
# stop the container holding the port
docker stop <container-id>
```

Or move the AI Engine to a different host port — remember that only the host
side changes; the container still listens on `8000`:

```bash
docker run --rm -p 8080:8000 -e PROVIDER=ollama \
  -e MODEL=llama3 \
  -e PROVIDER_BASE_URL=http://host.docker.internal:11434 \
  ai-engine
```

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

> Note: `PORT` in the environment does **not** change the listening port. The
> bind address is decided by the Uvicorn command line, and the Docker image's
> `CMD` hard-codes `--host 0.0.0.0 --port 8000`. See
> [section 16](#16-missing-environment-variable).

---

## 5. The health endpoint fails

**Problem**

`curl http://localhost:8000/health` returns a connection error, a timeout, or
nothing at all, while the process appears to be running.

**Cause**

- The process is not running, or it exited — see [section 1](#1-the-ai-engine-fails-to-start).
- It is bound to a different port or interface than you are querying.
- You are querying from outside a container/VM that does not publish the port.
- `HOST` was expected to widen the bind address but the Uvicorn flag governs it
  (see [section 16](#16-missing-environment-variable)).

**Check**

```bash
curl -i --max-time 5 http://localhost:8000/health
```

Look at the server's own log output for a startup line such as
`Uvicorn running on http://0.0.0.0:8000`. If there is no such line, the server
never started.

**Fix**

- Start the server with an explicit, reachable bind address:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
- When running in Docker, publish the port: `-p 8000:8000`.
- When running on a remote host, query the host's real address, not
  `localhost`, and confirm the port is allowed by the host firewall.

`/health` is a liveness probe only. **VERIFIED:** it always returns
`{"status":"ok"}` while the process is alive, it makes no provider call, and it
does not depend on configuration. If `/health` fails, the problem is the process
or the network — not the AI provider.

---

## 6. The readiness endpoint fails

**Problem**

`curl -i http://localhost:8000/ready` returns `503` with:

```json
{
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "The AI provider is not configured. Set PROVIDER and PROVIDER_API_KEY (if required) in the environment."
  }
}
```

**Cause**

`Settings.is_configured` in `app/config.py` returned `False`. That happens when:

- `PROVIDER` is set to an empty value, or
- `PROVIDER` is `openai` or `anthropic` and `PROVIDER_API_KEY` is not set.

**Check**

Print the effective, non-secret configuration (run this in the same environment
as the server process):

```bash
# bash / macOS / Linux
cd apps/ai-engine
python -c "from app.config import settings; print(settings.provider, settings.model, settings.provider_base_url, settings.request_timeout)"
printenv | grep -E '^(PROVIDER|MODEL|REQUEST_TIMEOUT)='
```

```powershell
# Windows PowerShell
cd apps\ai-engine
python -c "from app.config import settings; print(settings.provider, settings.model, settings.provider_base_url, settings.request_timeout)"
Get-ChildItem Env: | Where-Object { $_.Name -match '^(PROVIDER|MODEL|REQUEST_TIMEOUT)' }
```

> Do not print the whole `Settings` object — its dataclass representation
> includes `api_key`.

**Fix**

Set `PROVIDER` to a supported value and restart the process:

```bash
export PROVIDER=ollama
export MODEL=qwen3:8b
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
$env:PROVIDER = "ollama"
$env:MODEL = "qwen3:8b"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**VERIFIED — what a `200` from `/ready` does not mean.** Readiness makes **no
provider call**. It only checks that `PROVIDER` is non-empty and that a cloud
provider name has a key. A `200 {"status":"ready"}` therefore does not prove
that Ollama is reachable, that the model is pulled, or that a real analysis
request will succeed. `/health` failing means the process is down;
`/ready` failing means the process is not configured. Neither one tests the
provider path.

---

## 7. Ollama is unavailable

**Problem**

`POST /api/v1/code-understanding` returns:

```json
{
  "error": {
    "code": "PROVIDER_ERROR",
    "message": "The AI provider returned an error."
  }
}
```

and the server log shows `Provider error: Cannot connect to Ollama at ...`.

**Cause**

No HTTP server is answering at `PROVIDER_BASE_URL`. Ollama is an **external**
dependency — the AI Engine never starts, embeds, or supervises it. In a
container this is the normal state until Ollama is reachable from that
container.

**Check**

Ask Ollama directly, from the same host or container that runs the AI Engine:

```bash
curl -i --max-time 5 http://localhost:11434/api/tags
```

Inside a container, substitute the address the engine is actually configured
with. `curlimages/curl` is a throwaway helper image — it only needs to be pulled
once, and it is **not** part of this repository:

```bash
docker run --rm curlimages/curl:latest --max-time 5 http://host.docker.internal:11434/api/tags
```

**Fix**

- Start the Ollama daemon on the host:
  ```bash
  ollama serve
  ```
- Verify it answers: `curl http://localhost:11434/api/tags`
- Point the AI Engine at a reachable address (see
  [section 15](#15-wrong-provider_base_url)).
- Restart the AI Engine after changing any environment variable — `Settings` is
  built at import time.

**NOTE:** the AI Engine has no health check, retry, or back-off for an
unavailable provider. It fails the single request and returns.

---

## 8. Connection refused connecting to Ollama

**Problem**

The AI Engine logs `Cannot connect to Ollama at http://...:11434` and returns
`502 PROVIDER_ERROR`, even though Ollama is running on your machine.

**Cause**

The address the engine is using is not the address Ollama is listening on.
Almost always this is a container/host addressing mistake:

- Inside a container, `localhost` means **that container**, not your machine —
  see [section 15](#15-wrong-provider_base_url).
- Ollama's default port is `11434`; using `8000` (the AI Engine's own port) is a
  common typo.
- Ollama is bound to `127.0.0.1` on the host and not reachable from another
  interface or machine.

**Check**

```bash
# 1. What does the engine think its base URL is?
cd apps/ai-engine
python -c "from app.config import settings; print(settings.provider_base_url)"

# 2. Can that exact address be reached from the engine's environment?
curl -i --max-time 5 "$(python -c 'from app.config import settings; print(settings.provider_base_url)')/api/tags"
```

From a container:

```bash
docker run --rm curlimages/curl:latest --max-time 5 http://host.docker.internal:11434/api/tags
```

**Fix**

| Where the engine runs | Where Ollama runs | `PROVIDER_BASE_URL` |
|---|---|---|
| Host process | Host process | `http://localhost:11434` |
| Container | Host machine | `http://host.docker.internal:11434` |
| Container | Another container, same network | `http://<ollama-container-name>:11434` |
| Host process | Another machine | `http://<that-machine-ip>:11434` |

Then restart the engine so the new value is read. Also confirm the port is not
firewalled and that Ollama is listening on all interfaces, not only loopback.

---

## 9. Model unavailable

**Problem**

`POST /api/v1/code-understanding` returns `502 PROVIDER_ERROR`, the log shows
`Ollama returned HTTP 404`, and Ollama itself reports
`model 'qwen3:8b' not found, try pulling it first` (the upstream wording
modelled in `tests/fixtures/ollama_transport.py`).

**Cause**

The Ollama server is reachable and healthy, but the tag in `MODEL` is not
present on that server. A tag can be configured in the AI Engine and still be
missing from a specific Ollama instance, since each server has its own model
store.

**Check**

```bash
# which tags does this Ollama server actually have?
curl http://localhost:11434/api/tags

# what is the engine configured to ask for?
cd apps/ai-engine
python -c "from app.config import settings; print(settings.model)"
```

**Fix**

Either pull the tag on that server:

```bash
ollama pull qwen3:8b
```

or set `MODEL` to a tag that `/api/tags` already lists, then restart the engine:

```bash
export MODEL=llama3
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**VERIFIED:** a missing model surfaces as `502 PROVIDER_ERROR`, not as a crash
or a fabricated answer — `tests/integration/test_failure_states.py` asserts that
the response body contains no `summary` and that the upstream "try pulling it
first" text is not quoted back to the caller.

---

## 10. Provider timeout

**Problem**

`POST /api/v1/code-understanding` returns:

```json
{
  "error": {
    "code": "PROVIDER_TIMEOUT",
    "message": "The AI provider did not respond in time. Please try again."
  }
}
```

The log shows `Provider timeout: Ollama request timed out after <N>s`.

**Cause**

`OllamaProvider` passes `REQUEST_TIMEOUT` to `httpx`, and the request did not
complete within it. Common contributors: the model is large or cold (first load
into memory or onto disk is slow), the machine is under load or out of memory,
or generation genuinely runs longer than the budget.

**Check**

```bash
# the configured budget
cd apps/ai-engine
python -c "from app.config import settings; print(settings.request_timeout)"

# is the model itself able to answer a trivial prompt in time?
time curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

**Fix**

Raise the budget and restart the engine:

```bash
export REQUEST_TIMEOUT=300
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
$env:REQUEST_TIMEOUT = "300"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If a trivial `/api/chat` also times out, the problem is the Ollama side, not the
AI Engine: check that the model is loaded, that the machine has enough memory,
and that nothing else is saturating the host. If only the full analysis request
times out, see [section 18](#18-qwen38b-full-analysis-timeout-blocker) — that is a
known **BLOCKER**.

**VERIFIED:** connect/read timeouts map to `504 PROVIDER_TIMEOUT`, and the
configured budget is not disclosed in the response body. Timeout detection in
`app/main.py` is keyword-based on the provider message
(`"timed out"` / `"timeout"`).

---

## 11. Malformed provider response

**Problem**

`POST /api/v1/code-understanding` returns `502 PROVIDER_ERROR`, and the log
shows one of:

```text
Provider error: Ollama response parse error: 'message'
Provider error: Ollama response parse error: 'content'
Provider error: Ollama response parse error: Expecting value: line 1 column 1 (char 0)
```

**Cause**

Ollama answered with HTTP `200` but a body the provider cannot read.
`OllamaProvider.complete` requires `data["message"]["content"]`. Failures seen
in practice:

- JSON with no `message` key, or `message` with no `content` key.
- A non-JSON body — typically an HTML page from a reverse proxy, load balancer,
  or captive portal sitting in front of Ollama.
- An empty object `{}`.

**Check**

Inspect the raw body the engine would receive:

```bash
curl -i http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

Confirm the base URL points at Ollama and not at a proxy:

```bash
cd apps/ai-engine
python -c "from app.config import settings; print(settings.provider_base_url)"
```

**Fix**

- Make sure `PROVIDER_BASE_URL` addresses Ollama directly, with no proxy, load
  balancer, or auth gateway rewriting responses.
- Confirm the model tag responds with a normal Ollama chat envelope
  (`{"model": ..., "message": {"role": "assistant", "content": ...}, "done": true}`).
- If a reverse proxy is required, configure it to pass the JSON body through
  unchanged.

**VERIFIED:** a malformed body always produces `502 PROVIDER_ERROR` and never a
fabricated `summary`; the upstream body is not reflected in the response
(`tests/integration/test_failure_states.py`).

---

## 12. Invalid input or HTTP 422

**Problem**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed."
  }
}
```

**Cause**

The request body failed Pydantic validation in
`app/schemas/code_understanding.py`. **VERIFIED** rules that cause a `422`:

| Rule | Detail |
|---|---|
| `source_code` required | Missing, or whitespace-only |
| `source_code` max length | 100 000 characters |
| `language` required | Must be one of the `ProgrammingLanguage` enum values (lowercase) |
| `file_path` optional | Max 1 024 characters; a present value must not be blank |
| `question` optional | Max 10 000 characters; a present value must not be blank |
| `context` optional | Max 50 000 characters; a present value must not be blank |
| `analyses` optional | Defaults to all five; minimum 1; unknown values rejected |
| Unknown fields | Rejected — the schema is `extra="forbid"` |

Note that `message` is a fixed string; the specific field is **not** returned to
the caller by design.

**Check**

Reproduce the rejection against the running service, with a payload that
violates one rule at a time:

```bash
curl -i -X POST http://localhost:8000/api/v1/code-understanding \
  -H "Content-Type: application/json" \
  -d '{"source_code":"   ","language":"python"}'
```

`/docs` (Swagger UI) shows the full per-field validation detail that the API
response deliberately omits:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/docs -Method Get
```

To see the underlying Pydantic message locally, validate the payload in Python:

```bash
cd apps/ai-engine
python -c "from app.schemas.code_understanding import CodeUnderstandingRequest as R; R.model_validate({'source_code':'  ','language':'python'})"
```

**Fix**

- Send `source_code` (non-blank) and `language` (valid enum value).
- Remove any field the schema does not declare.
- Omit optional fields you do not need rather than sending `""` or `null` for
  `question`, `context`, or `file_path` — a present-but-blank value is rejected.
- Keep payloads within the documented length limits.

**VERIFIED:** validation happens before the provider is used, so a rejected
request never consumes model capacity, and the submitted payload is not echoed
back.

---

## 13. Docker build failure

**Problem**

```text
ERROR: failed to solve: process "/bin/sh -c pip install --no-cache-dir -r requirements.txt" did not complete successfully
```

or

```text
COPY failed: file not found in build context
```

**Cause**

- `pip` could not reach the package index from inside the build (see
  [section 2](#2-python-dependency-installation-fails) for the Python-level
  equivalent).
- The build was run from the wrong directory, so `requirements.txt` and `app/`
  are not in the build context. The `Dockerfile` uses `COPY requirements.txt .`
  and `COPY app ./app`, both relative to the build context.
- A dependency needs a compiler or system library that `python:3.11-slim` does
  not provide. No build tools are installed in the image.

**Check**

```bash
cd apps/ai-engine
ls requirements.txt Dockerfile
docker build -t ai-engine . --progress=plain
```

Confirm the context is not polluted — `.dockerignore` should exclude `.venv/`,
`__pycache__/`, `.pytest_cache/`, `*.log`, `.env`, `.env.*`, `tests/`, and
`pytest.ini`:

```bash
cat .dockerignore
```

**Fix**

- Always build from `apps/ai-engine`:
  ```bash
  cd apps/ai-engine
  docker build -t ai-engine .
  ```
- If the package index is unreachable from the build, fix connectivity for the
  Docker daemon (proxy settings, VPN, or an internal mirror that `pip` inside the
  build can reach) and rebuild. The `Dockerfile` declares no build arguments, so
  there is no in-repo knob to set.
- If a dependency needs system packages, that requires a `Dockerfile` change —
  `Dockerfile` is out of scope for this document; do not work around it by
  installing into the image at run time.

---

## 14. Docker container startup failure

**Problem**

```text
docker: Error response from daemon: driver failed programming external connectivity
```

or the container starts and immediately exits:

```text
ai-engine_1  ... Exited (1) 0.2 seconds ago
```

**Cause**

- The host port `8000` is already taken — see
  [section 4](#4-port-8000-is-already-in-use).
- The container cannot construct a provider because `PROVIDER` is unset to a
  supported value, giving `503` on every request.
- A `uvicorn` import failure inside the image (the container logs the same
  messages as [section 1](#1-the-ai-engine-fails-to-start)).
- The image has no `HEALTHCHECK` instruction, so a broken container stays
  "running"-looking with no automatic signal.

**Check**

```bash
docker ps -a --filter "ancestor=ai-engine"
docker logs <container-id>
```

Verify the image itself is sound — the app imports and the runtime user is
non-root:

```bash
docker run --rm --entrypoint python ai-engine -c "import app.main; print('app ok')"
docker run --rm --entrypoint id ai-engine
```

Confirm the environment actually reached the container:

```bash
docker inspect <container-id> --format '{{range .Config.Env}}{{println .}}{{end}}'
```

**Fix**

- Free port `8000` or publish a different host port (`-p 8080:8000`).
- Pass the provider variables explicitly on `docker run` (see
  [README Docker deployment](README.md#docker-deployment)):
  ```bash
  docker run --rm -p 8000:8000 \
    -e PROVIDER=ollama \
    -e MODEL=qwen3:8b \
    -e PROVIDER_BASE_URL=http://host.docker.internal:11434 \
    -e REQUEST_TIMEOUT=60 \
    ai-engine
  ```
- Read `docker logs` for the real error before changing anything else.

**VERIFIED:** the image runs as the non-root user `appuser` (UID/GID `10001`).
If a command needs to write into `/app`, that is expected to fail — nothing in
the image writes to disk.

---

## 15. Wrong `PROVIDER_BASE_URL`

**Problem**

It works on the host and fails in Docker: `502 PROVIDER_ERROR` with
`Cannot connect to Ollama at http://localhost:11434` in the container log. The
same class of failure occurs on a Linux Docker engine, where
`host.docker.internal` is not defined by default and a host-machine Ollama is
therefore unreachable by that name.

**Cause**

> **`localhost` inside a container means the container itself.**
> In a container, `localhost` / `127.0.0.1` resolves to *that container's own
> network namespace*. It does not reach the host machine and it does not reach
> any other container. The AI Engine image contains no Ollama server, so
> `PROVIDER_BASE_URL=http://localhost:11434` inside a container always points at
> a process that does not exist there.

`PROVIDER_BASE_URL` must be the address of the Ollama server **as seen from the
process that makes the request**, which is the AI Engine, not your shell.

**Check**

From inside a container, test the address you intend to use:

```bash
docker run --rm curlimages/curl:latest --max-time 5 http://host.docker.internal:11434/api/tags
docker run --rm curlimages/curl:latest --max-time 5 http://<ollama-container-name>:11434/api/tags
```

On Linux, add the host gateway explicitly and check it is present:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway \
  curlimages/curl:latest --max-time 5 http://host.docker.internal:11434/api/tags
```

**Fix**

| Setup | `PROVIDER_BASE_URL` |
|---|---|
| Engine and Ollama both native on one host | `http://localhost:11434` |
| Engine in Docker, Ollama on the Docker host (Docker Desktop) | `http://host.docker.internal:11434` |
| Engine in Docker on Linux, Ollama on the Docker host | `http://host.docker.internal:11434` **plus** `--add-host=host.docker.internal:host-gateway` |
| Engine in Docker, Ollama in a container on the same user-defined network | `http://<ollama-container-name>:11434` |
| Engine in Docker, Ollama on another machine | `http://<host-or-service-ip>:11434` |

**NOT IMPLEMENTED:** this repository contains no `docker-compose.yml`, no
Ollama service definition, and no automatic network wiring. If you use Compose
or `docker network`, you are introducing that configuration yourself; the engine
only reads `PROVIDER_BASE_URL`.

---

## 16. Missing environment variable

**Problem**

A setting appears to be ignored — for example the server still binds to port
`8000` after you changed `PORT`, or `MODEL` has no effect. Or `/ready` reports
`PROVIDER_UNAVAILABLE`.

**Cause**

- The variable was set in a different shell than the one that started the
  process. `app/config.py` reads `os.getenv` when `Settings` is constructed at
  import time, so the value must exist **before** the process starts. Exporting
  it in a later shell does not affect a running process.
- `HOST` and `PORT` are read into `settings` but **nothing in the application
  reads them back** (**VERIFIED**). The bind address is decided by the Uvicorn
  command line; the Docker image's `CMD` hard-codes `--host 0.0.0.0 --port 8000`.
  So `HOST`/`PORT` are effectively informational.
- A variable was set only for a one-off command and is absent in the service
  manager, container, or scheduled task that actually runs the process.

**Check**

```bash
# bash / macOS / Linux — in the same shell that starts the server
printenv | grep -E '^(PROVIDER|MODEL|PROVIDER_BASE_URL|REQUEST_TIMEOUT)='
```

```powershell
# Windows PowerShell
Get-ChildItem Env: | Where-Object { $_.Name -match '^(PROVIDER|MODEL|PROVIDER_BASE_URL|REQUEST_TIMEOUT)' }
```

Confirm what the code actually resolves (from `apps/ai-engine`):

```bash
python -c "from app.config import settings; print(settings.provider, settings.model, settings.provider_base_url, settings.request_timeout)"
```

Confirm the container received it:

```bash
docker inspect <container-id> --format '{{range .Config.Env}}{{println .}}{{end}}'
```

**Fix**

- Set the variable in the same shell, then start the process:
  ```bash
  export REQUEST_TIMEOUT=120
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
  ```powershell
  $env:REQUEST_TIMEOUT = "120"
  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
- Restart the process after every configuration change.
- For `HOST`/`PORT`, pass the Uvicorn flags instead of relying on the variables:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8080
  ```
- In a container, set variables with `-e` on `docker run` (see
  [section 17](#17-env-is-ignored) for why a mounted `.env` file does nothing).
- Under a service manager, define the variables in that manager's unit/environment
  configuration rather than relying on an interactive shell.

---

## 17. `.env` is ignored

**Problem**

You created `apps/ai-engine/.env` (or copied `.env.example` to `.env`), filled it
in, and the application still uses the built-in defaults — so changing
`MODEL`, `REQUEST_TIMEOUT`, or `PROVIDER_BASE_URL` in the file appears to have
no effect at all.

**Cause**

**VERIFIED:** the AI Engine does not read `.env`, by design.

- `python-dotenv` is **not** in `requirements.txt`.
- Nothing in `app/` calls `load_dotenv` or reads any file; `app/config.py` uses
  `os.getenv` only.
- `apps/ai-engine/.env.example` is a **reference/template** listing the
  supported variables and their defaults. It is not a runtime input, and
  `.dockerignore` excludes `.env` from the build context.

**Check**

```bash
cd apps/ai-engine
# a .env here is inert — confirm there is no loader anywhere:
grep -rn "load_dotenv\|dotenv" app/ requirements.txt
```

```powershell
# Windows PowerShell
Select-String -Path app\*.py,app\**\*.py,requirements.txt -Pattern "load_dotenv|dotenv"
```

Verify what the process really sees (see
[section 16](#16-missing-environment-variable)).

**Fix**

Load the values into the environment yourself before starting the process.

bash / macOS / Linux:

```bash
cd apps/ai-engine
set -a
. ./.env
set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
cd apps\ai-engine
Get-Content .\.env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' -and $_ -notmatch '^\s*#' } | ForEach-Object {
  $name, $value = $_ -split '=', 2
  Set-Item -Path "Env:$name" -Value $value
}
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For a container, pass variables with `-e` explicitly; the image never reads a
file.

**If `.env` is tracked in Git, remove it.** The repository root `.gitignore`
already excludes `.env` and `.env.*` while keeping `!.env.example`, but an
explicitly force-added file is still tracked:

```bash
git rm --cached apps/ai-engine/.env
```

**Secret handling:** never commit real credentials. `.env.example` is the only
`.env*` file that belongs in the repository, and it contains no secrets. See
[Secret handling](README.md#secret-handling).

---

## 18. `qwen3:8b` full-analysis timeout (BLOCKER)

**Status: BLOCKER — diagnosed, not fixed.**

**Problem**

Ollama itself is healthy, but a full code-understanding request never returns:

```json
{
  "error": {
    "code": "PROVIDER_TIMEOUT",
    "message": "The AI provider did not respond in time. Please try again."
  }
}
```

Raising `REQUEST_TIMEOUT` to `300` does not help.

**Cause**

The failure is in the **provider path**, not in the AI Engine's orchestration,
validation, or error handling, and not in your Ollama installation.

**VERIFIED facts (Phase 13 diagnosis, recorded in
`tests/integration/test_failure_states.py`):**

| Fact | Status |
|---|---|
| `qwen3:8b` exists on the Ollama server | VERIFIED |
| `GET /api/tags` is reachable and lists the model | VERIFIED |
| A simple `POST /api/chat` with a short prompt succeeds | VERIFIED |
| `POST /api/v1/code-understanding` (full analysis) times out | VERIFIED |
| The timeout reproduces at both `REQUEST_TIMEOUT=60` and `REQUEST_TIMEOUT=120` | VERIFIED |
| The blocker is the provider path in `app/providers/ollama.py` | VERIFIED |

Two concrete code facts explain why, and both are visible in
`app/providers/ollama.py`:

- The request is sent with `"stream": False` and **no generation cap** — the
  payload contains only `model`, `messages`, `stream`, and (optionally)
  `options.temperature`. There is no `num_predict` and no thinking-mode control.
- Only `data["message"]["content"]` is read. `qwen3:8b` is a thinking model, so
  its reasoning trace arrives in `message.thinking`, which the provider
  discards; with no generation cap and `stream: False`, generation does not
  finish inside the read timeout.

**Check**

Confirm each layer independently:

```bash
# 1. model present?
curl http://localhost:11434/api/tags

# 2. trivial chat works?
time curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"hi"}],"stream":false}'

# 3. the full request times out
time curl -i -X POST http://localhost:8000/api/v1/code-understanding \
  -H "Content-Type: application/json" \
  -d '{"source_code":"def add(a, b):\n    return a + b\n","language":"python","analyses":["explanation"]}'
```

**Fix**

**There is no fix available in this repository today.** The defect belongs to the
OllamaProvider architecture, and the fix is **NOT IMPLEMENTED** — it is not a
configuration option you can turn on. Do not be told otherwise:

- Raising `REQUEST_TIMEOUT` only moves the deadline; it does not make generation
  terminate.
- No streaming support, generation cap, or thinking-mode handling exists in
  `OllamaProvider` today. Any suggestion to "just add" one is a proposed change,
  not an available configuration.
- The test suite deliberately does **not** exercise this path. The timeout is
  covered as a deterministic transport condition in
  `tests/integration/test_failure_states.py`, so the suite stays fast and
  reproducible.

What you can do in the meantime, all of them configuration-level and none of
them a fix for the provider defect:

- Use a model tag that answers within your budget, if one is available on your
  Ollama server (`ollama list`).
- Set an explicit `REQUEST_TIMEOUT` that matches the operational expectation
  your callers can tolerate.
- Treat `504 PROVIDER_TIMEOUT` as a retryable condition in callers. The engine
  never fabricates an answer when this happens, and the response body contains
  no `summary`.

---

## Related documentation

- [`README.md`](README.md) — configuration reference, deployment, HTTP contract,
  test suite, and the list of known limitations.
- `app/config.py` — the only place environment variables are read.
- `app/main.py` — routes and the HTTP status mapping.
- `app/providers/ollama.py` — the provider request payload and error translation.
- `Dockerfile` — image contents, non-root user, and the default command.
- `tests/integration/test_failure_states.py` — the eight failure states as
  automated, verified checks.
