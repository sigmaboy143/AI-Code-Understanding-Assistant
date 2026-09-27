# AI Engine

The AI Engine is the core intelligence layer of the AI-Code-Understanding-Assistant project.
It provides:

- A FastAPI HTTP service for code understanding via an LLM provider abstraction
- A grounded reasoning layer that constructs analysis-aware, anti-fabrication prompts
- A provider-independent retrieval foundation (lexical in-memory retriever)
- A centralised context builder that selects, deduplicates, and caps context before it reaches the LLM
- An evidence and confidence model that attributes where information came from
- An output validation pipeline that normalises and validates raw LLM responses

The service is implemented with **Python** and **FastAPI** and is modular so that
capabilities (vector stores, specialised agents) can be added incrementally.

---

## Prerequisites

- Python 3.11 or later
- `pip`

---

## Setup

### 1. Create a virtual environment

```bash
cd apps/ai-engine
python -m venv .venv
```

Activate it:

- **macOS / Linux**
  ```bash
  source .venv/bin/activate
  ```
- **Windows (PowerShell)**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

The AI Engine reads configuration **only from the process environment**, via
`os.getenv()` in `app/config.py`.

> **`.env` is NOT loaded.** `python-dotenv` is not a dependency of this service,
> so creating a `.env` file has no effect — the application will keep using the
> built-in defaults. Configuration must be supplied by the shell, the service
> manager, or the container runtime that starts the process.

`.env.example` is a **reference/template**: it lists the supported variables and
their default values. It is not read at runtime.

**Windows (PowerShell)**

```powershell
$env:HOST               = "0.0.0.0"
$env:PORT               = "8000"
$env:PROVIDER           = "ollama"
$env:MODEL              = "llama3"
$env:PROVIDER_BASE_URL  = "http://localhost:11434"
$env:REQUEST_TIMEOUT    = "60"
# $env:PROVIDER_API_KEY  = "..."   # cloud providers only, not used by Ollama

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**macOS / Linux (bash / zsh)**

```bash
export HOST=0.0.0.0
export PORT=8000
export PROVIDER=ollama
export MODEL=llama3
export PROVIDER_BASE_URL=http://localhost:11434
export REQUEST_TIMEOUT=60
# export PROVIDER_API_KEY=...   # cloud providers only, not used by Ollama

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Running the service

Set the environment variables (see [Setup](#3-configure-environment-variables))
in the same shell that starts the process, then run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at <http://localhost:8000>.

Interactive docs (Swagger UI): <http://localhost:8000/docs>

---

## Provider configuration

All settings are read from environment variables supplied to the process.
No credentials are hard-coded anywhere, and **no `.env` file is read** —
`python-dotenv` is not a dependency. `.env.example` is a reference/template for
the variables below, not a file the application consumes.

| Variable           | Default                    | Description                                                           |
|--------------------|----------------------------|-----------------------------------------------------------------------|
| `HOST`             | `0.0.0.0`                  | Network interface to bind                                             |
| `PORT`             | `8000`                     | TCP port                                                              |
| `PROVIDER`         | `ollama`                   | LLM provider: `ollama` (only supported value currently)              |
| `MODEL`            | `llama3`                   | Model name forwarded to the provider                                  |
| `PROVIDER_BASE_URL`| `http://localhost:11434`   | Base URL for self-hosted providers (Ollama)                           |
| `REQUEST_TIMEOUT`  | `60`                       | Seconds to wait for a provider response before raising a 504 error   |
| `PROVIDER_API_KEY` | *(not set)*                | API key for cloud providers (OpenAI, Anthropic). Not used for Ollama |

> **Note:** `HOST` and `PORT` are read by `app/config.py`. When you start the
> server with `uvicorn --host ... --port ...`, those CLI flags take precedence
> over the variables.

### Running with Docker

The image takes its configuration from environment variables passed to the
container. No `.env` file is copied into or read by the image.

```bash
cd apps/ai-engine
docker build -t ai-engine .

docker run --rm -p 8000:8000 \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -e PROVIDER=ollama \
  -e MODEL=llama3 \
  -e PROVIDER_BASE_URL=http://host.docker.internal:11434 \
  -e REQUEST_TIMEOUT=60 \
  ai-engine
```

Add `-e PROVIDER_API_KEY=...` only for cloud providers. When Ollama runs on the
host machine, `host.docker.internal` is used above so the container can reach it.

---

## API endpoints

### `GET /health`

Liveness check. Always returns `200 OK` while the process is running.

**Response**
```json
{"status": "ok"}
```

---

### `GET /ready`

Readiness check. Returns `200` when the service has the minimum configuration
required to accept requests.

**No real LLM call is made.** The check verifies only:
- A provider name is set (`PROVIDER` env var is non-empty).
- Cloud providers that require an API key (`openai`, `anthropic`) have one configured.

**200 — ready**
```json
{"status": "ready"}
```

**503 — not configured**
```json
{
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "The AI provider is not configured. ..."
  }
}
```

---

### `POST /api/v1/code-understanding`

Analyse source code using the configured LLM provider.

#### Request body — `CodeUnderstandingRequest`

| Field         | Type                        | Required | Constraints                     | Description                                          |
|---------------|-----------------------------|----------|---------------------------------|------------------------------------------------------|
| `source_code` | `string`                    | ✅        | non-blank, max 100 000 chars    | Raw source code to analyse                           |
| `language`    | `ProgrammingLanguage` enum  | ✅        | see enum values below           | Language of the source code                          |
| `file_path`   | `string \| null`            | ❌        | non-blank, max 1 024 chars      | Repository-relative path (for context in the prompt) |
| `question`    | `string \| null`            | ❌        | non-blank, max 10 000 chars     | Free-form question to answer                         |
| `context`     | `string \| null`            | ❌        | non-blank, max 50 000 chars     | Additional context: error output, related code, etc. |
| `analyses`    | `AnalysisType[]`            | ❌        | min 1, deduped; defaults to all | Which analyses to perform                            |

**`ProgrammingLanguage` values:** `python`, `typescript`, `javascript`, `java`, `c`, `cpp`, `csharp`, `go`, `rust`, `ruby`, `php`, `kotlin`, `swift`, `sql`, `shell`, `html`, `css`, `other`

**`AnalysisType` values:** `explanation`, `error_explanation`, `structure`, `dependencies`, `improvements`

**Example request**
```json
{
  "source_code": "def add(a, b):\n    return a + b\n",
  "language": "python",
  "file_path": "src/math.py",
  "question": "Does this handle None inputs?",
  "analyses": ["explanation", "improvements"]
}
```

#### Response body — `CodeUnderstandingResponse`

| Field               | Type                        | Always present | Description                                                        |
|---------------------|-----------------------------|----------------|--------------------------------------------------------------------|
| `summary`           | `string`                    | ✅             | Overall plain-language summary (from LLM output)                   |
| `explanation`       | `CodeExplanation \| null`   | ❌             | Detailed code explanation (not populated currently)                 |
| `error_explanation` | `ErrorExplanation \| null`  | ❌             | Error/bug explanation (not populated currently)                     |
| `structure`         | `StructureAnalysis \| null` | ❌             | Structural outline (not populated currently)                        |
| `dependencies`      | `DependencyAnalysis \| null`| ❌             | Dependency analysis (not populated currently)                       |
| `improvements`      | `ImprovementSuggestion[]`   | ✅ (empty)     | Improvement suggestions (not populated currently)                   |
| `metadata`          | `AnalysisMetadata`          | ✅             | Language, file path, analyses performed                             |
| `confidence`        | `ResponseConfidence \| null`| ✅             | Evidence-backed confidence (CONFIRMED/INFERRED/UNKNOWN); see below |

> **Note:** Currently the LLM's free-text completion is placed into `summary`.
> The optional structured fields (`explanation`, `structure`, `dependencies`, `improvements`)
> are schema-ready but are not populated by the current response parser — they require
> structured extraction to be added to `_parse_response` in a future task.

**Example response**
```json
{
  "summary": "The add function takes two arguments and returns their sum.",
  "explanation": null,
  "error_explanation": null,
  "structure": null,
  "dependencies": null,
  "improvements": [],
  "metadata": {
    "language": "python",
    "file_path": "src/math.py",
    "analyses": ["explanation", "improvements"],
    "confidence": null
  },
  "confidence": {
    "level": "UNKNOWN",
    "evidence": [
      {
        "source_type": "source_code",
        "file_path": "src/math.py",
        "line_start": null,
        "line_end": null,
        "chunk_id": null,
        "description": "Submitted source code (available to model; claims not individually verified)."
      }
    ],
    "notes": "Free-text response: claims not individually mapped to evidence. Source code listed as available context."
  }
}
```

---

## Error responses

All non-2xx responses use the same JSON envelope:

```json
{
  "error": {
    "code": "SCREAMING_SNAKE_CASE",
    "message": "Human-readable description. No secrets or stack traces."
  }
}
```

| HTTP status | `error.code`           | Cause                                                              |
|-------------|------------------------|--------------------------------------------------------------------|
| `422`       | `VALIDATION_ERROR`     | Request body fails Pydantic validation                             |
| `503`       | `PROVIDER_UNAVAILABLE` | Provider cannot be constructed or service is not configured        |
| `504`       | `PROVIDER_TIMEOUT`     | Provider did not respond within `REQUEST_TIMEOUT` seconds          |
| `502`       | `PROVIDER_ERROR`       | Provider returned an error or a malformed response                 |
| `500`       | `INTERNAL_ERROR`       | Unexpected server-side failure                                     |

API keys, stack traces, and internal exception messages are **never** included in error responses.

---

## Context Builder (`app/context_builder/`)

The context builder is a centralised, provider-independent layer that sits between
the retrieval layer and the reasoning/orchestrator pipeline.

### Flow

```
CodeUnderstandingRequest
        ↓
Retriever (optional)
        ↓
Retrieved Chunks
        ↓
ContextBuilder.build()
        ↓
BuiltContext (deduplicated, size-capped, ordered)
        ↓
Reasoning / Orchestrator
        ↓
LLM Provider
```

### What it does

1. **Combines relevant information** — source code, file path, language, user question,
   requested analyses, optional supplementary context, and retrieved chunks.
2. **Deduplicates retrieved chunks** by `chunk_id` — the same content is never included twice.
3. **Applies a size/character cap** (`MAX_CONTEXT_CHARS = 80 000` by default) — when the
   total character count of all context sections would exceed this limit, lower-relevance
   chunks are dropped first.
4. **Preserves source attribution** — every included chunk retains its `chunk_id`,
   `file_path`, `line_start`, `line_end`, `symbol`, and `source_type` for use by the
   evidence layer.
5. **Deterministic** — same input always produces the same `BuiltContext`.
6. **Sets a `truncated` flag** when chunks were dropped to satisfy the budget.

### Data model — `BuiltContext`

| Field             | Type                  | Description                                           |
|-------------------|-----------------------|-------------------------------------------------------|
| `source_code`     | `str`                 | Submitted source code                                 |
| `language`        | `ProgrammingLanguage` | Programming language                                  |
| `file_path`       | `str \| None`         | Repository-relative path                              |
| `question`        | `str \| None`         | User question                                         |
| `user_context`    | `str \| None`         | Supplementary context from the request                |
| `analyses`        | `list[AnalysisType]`  | Requested analysis types                              |
| `included_chunks` | `list[IncludedChunk]` | Deduplicated, sorted, budget-trimmed retrieved chunks |
| `truncated`       | `bool`                | `True` when chunks were dropped to fit the budget     |
| `extra_sections`  | `dict[str, str]`      | Reserved for future evidence types (always empty now) |

### Extension points (not yet implemented)

- Git evidence: populate `extra_sections["git"]` or add a dedicated field.
- Test evidence: same pattern.
- Relationship / architecture context: same pattern.

### Actual limitations

- No semantic ranking — relies on the retrieval layer's `relevance_score`.
- Size limit applies to chunks only; source code is always included regardless of size.
- `extra_sections` is always empty at this milestone.

---

## Evidence Model (`app/evidence/`)

The evidence model identifies where supporting information in a response came from.
Evidence is never invented automatically.

### Evidence source types — `EvidenceSourceType`

| Value              | Meaning                                                          |
|--------------------|------------------------------------------------------------------|
| `source_code`      | From the submitted source code                                   |
| `retrieved_chunk`  | From a retrieved context chunk (RAG)                            |
| `file`             | From a referenced file path                                      |
| `documentation`    | From inline documentation or docstrings                          |
| `test`             | From test code (reserved; not automatically populated)           |
| `git_commit`       | From Git history (reserved; **never fabricated automatically**)  |

### Evidence item — `EvidenceItem`

| Field         | Type                      | Description                                      |
|---------------|---------------------------|--------------------------------------------------|
| `source_type` | `EvidenceSourceType`      | Where the evidence came from                     |
| `file_path`   | `str \| None`             | Repository-relative file path                    |
| `line_start`  | `int \| None`             | First line (1-based)                             |
| `line_end`    | `int \| None`             | Last line (1-based)                              |
| `chunk_id`    | `str \| None`             | Chunk identifier (when source is retrieved_chunk)|
| `description` | `str \| None`             | Short human-readable reference                   |

---

## Confidence Model (`app/evidence/models.py`)

### Three-state confidence — `ConfidenceLevel`

| State       | Meaning                                                                                        |
|-------------|------------------------------------------------------------------------------------------------|
| `CONFIRMED` | A **specific structured claim** is directly supported by a verified evidence item.            |
| `INFERRED`  | Reasoned from available evidence but not explicitly established.                               |
| `UNKNOWN`   | Insufficient evidence, or the claim has not been individually mapped to evidence.             |

> **Important:** `CONFIRMED` is only appropriate when a specific claim has been
> directly and individually verified against an evidence item.  The presence of
> source code or retrieved chunks in the prompt does **not** confirm the model's
> free-text answer — it only establishes what was available to the model.

### `ResponseConfidence`

| Field      | Type                  | Default   | Description                                           |
|------------|-----------------------|-----------|-------------------------------------------------------|
| `level`    | `ConfidenceLevel`     | `UNKNOWN` | Confidence state                                      |
| `evidence` | `list[EvidenceItem]`  | `[]`      | Evidence items supporting this level                  |
| `notes`    | `str \| None`         | `None`    | Optional explanatory note                             |

### Constructors

| Constructor                  | Level       | Use case                                                                     |
|------------------------------|-------------|------------------------------------------------------------------------------|
| `unknown()`                  | `UNKNOWN`   | No evidence available at all                                                 |
| `unknown_with_source_code()` | `UNKNOWN`   | Free-text LLM answer; source code was available but claims not verified      |
| `unknown_with_chunks()`      | `UNKNOWN`   | Free-text LLM answer; retrieved chunks were available but claims not verified|
| `from_source_code()`         | `CONFIRMED` | A **structured claim** directly and fully supported by the source code       |
| `from_chunks()`              | `CONFIRMED` | A **structured claim** directly backed by specific retrieved chunks          |

### Current confidence assignment logic (free-text response pipeline)

- **Free-text LLM response, no retrieved chunks** → `UNKNOWN`, evidence list records the source-code reference.
- **Free-text LLM response, retrieved chunks in prompt** → `UNKNOWN`, evidence list records the chunk references.
- In both cases the `evidence` list is non-empty so callers can see what the model had access to.
- `CONFIRMED` is **not** assigned automatically by the free-text pipeline.
- `INFERRED` is not automatically assigned by the current pipeline.

### Current limitations

- Claim-level evidence mapping is not implemented; individual model statements in a
  free-text answer cannot be verified against evidence items.
- There is no numeric confidence score — none is calculated.
- `git_commit`, `test`, and `documentation` evidence types are never automatically populated.

---

## Output Validation (`app/output_validation/`)

The output validation pipeline prevents raw LLM output from being passed directly
to the caller without sanity checks.

### Pipeline

```
LLM output (LLMResponse)
        ↓
Extract content string
        ↓
Validate (detect empty / whitespace-only content)
        ↓
Normalise whitespace (strip, collapse 3+ blank lines)
        ↓
Truncate if > 10 000 characters
        ↓
Determine evidence reference + confidence level
        ↓
Return (summary_text, ResponseConfidence)
```

### Behaviour

| Input                    | Output                                     |
|--------------------------|--------------------------------------------|
| Valid non-empty content  | Content stripped and normalised            |
| Empty string             | Fallback: `"No summary produced by provider."` |
| Whitespace only          | Fallback: `"No summary produced by provider."` |
| Content > 10 000 chars   | Truncated to 10 000 chars + `" [truncated]"` |
| `ProviderError` raised   | Propagated directly — not caught here      |

### Confidence semantics for free-text responses

The free-text LLM path **always** produces `UNKNOWN` confidence.
Available inputs are recorded as evidence references but do not confirm the model's claims:

| Available inputs             | `confidence.level` | `confidence.evidence`                      |
|------------------------------|--------------------|--------------------------------------------|
| Source code only (no chunks) | `UNKNOWN`          | One `source_code` item recording the file  |
| Retrieved chunks in prompt   | `UNKNOWN`          | One `retrieved_chunk` item per chunk       |

`CONFIRMED` is only used for future structured-extraction paths where individual
claims are verified directly against evidence.

### Guarantees

- Never raises for empty or malformed content — returns the fallback summary.
- Never silently converts malformed output into fabricated data.
- Never exposes provider secrets or stack traces.
- `ProviderError` is propagated unchanged to the FastAPI layer for correct HTTP mapping.
- Source code or retrieved context availability does **not** elevate response confidence
  to `CONFIRMED`.

### `OutputValidationError`

A dedicated exception class for cases where the validator determines the response
is fundamentally unusable. Currently not raised by the free-text path (fallback is used
instead); reserved for future structured JSON validation.

### Current limitations

- The provider currently returns free-text. There is no JSON parsing or structured
  extraction. Optional structured fields in `CodeUnderstandingResponse`
  (`explanation`, `structure`, `dependencies`, `improvements`) remain `null`.
- Claim-level evidence mapping is not implemented; individual model statements are
  not verified against evidence.
- Confidence is always `UNKNOWN` on the free-text path.

---

## Reasoning layer (`app/reasoning.py`)

The reasoning layer is the single place where `CodeUnderstandingRequest` → `LLMRequest`
translation happens.

**Prompt design:**
- The system prompt explicitly forbids the model from fabricating repository facts
  (Git history, commits, tests, dependencies) not present in the supplied input.
- Each requested `AnalysisType` generates a numbered, concrete instruction.
- When a `question` is present it is prioritised above general analyses.
- When supplementary `context` is present it is injected as ground truth.
- The prompt contains a trailing reminder to acknowledge missing information explicitly.
- An optional `retrieved_chunks` parameter (list of `RetrievedChunk`) can be passed to
  inject RAG context — this is the Task 7 extension point.

**Actual limitations:**
- Single-turn only; no multi-agent orchestration.
- Free-text LLM output goes into `summary`; no structured JSON extraction.
- No confidence scoring from the LLM.
- Git history, commits, and PRs are never inferred automatically.

---

## Retrieval architecture (`app/retrieval/`)

The retrieval package provides a provider-independent foundation for context retrieval.

### Data model — `RetrievedChunk`

A Pydantic model representing one unit of retrieved context:

| Field            | Type           | Description                                               |
|------------------|----------------|-----------------------------------------------------------|
| `chunk_id`       | `str`          | Stable unique identifier                                  |
| `file_path`      | `str`          | Repository-relative path of the source file              |
| `symbol`         | `str \| null`  | Qualified symbol name, e.g. `MyClass.method`              |
| `content`        | `str`          | Text content (source snippet, doc comment, etc.)          |
| `line_start`     | `int \| null`  | First line (1-based)                                      |
| `line_end`       | `int \| null`  | Last line (1-based)                                       |
| `relevance_score`| `float`        | Retriever-assigned score in [0.0, 1.0]                    |
| `source_type`    | `str`          | e.g. `"source_code"`, `"docstring"`, `"comment"`          |

### Retriever interface — `RetrieverBase`

```python
class RetrieverBase(ABC):
    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]: ...
```

Any concrete retriever (vector, keyword, hybrid) implements this interface.
The orchestrator and reasoning layer only depend on `RetrieverBase`.

### Current implementation — `InMemoryRetriever`

A deterministic, dependency-free lexical retriever:

- **Algorithm:** token overlap — counts how many unique query tokens appear in
  each chunk's content; score = matched / total unique query tokens ∈ [0.0, 1.0].
- **Deterministic:** same query always returns the same ranked list.
- **No external dependencies:** pure Python standard library.
- **Easy to replace:** swap with a vector retriever by implementing `RetrieverBase`.

**Actual limitations:**
- No stemming, TF-IDF, or BM25 weighting.
- Not suitable for production use with large corpora.
- This is a local/lexical foundation, not production RAG.
- No external vector database or embedding service is used.

---

## AI Orchestrator (`app/orchestrator/`)

`OrchestratorService` coordinates a code-understanding request end-to-end:

```
CodeUnderstandingRequest
        ↓
ContextBuilder.build()                     ← Task 8: assemble + deduplicate context
        ↓
OrchestratorService._build_llm_request()  ← delegates to app.reasoning
        ↓                                    (included chunks injected here)
LLMProvider.complete()                     ← provider-agnostic call
        ↓
validate_llm_response()                    ← Task 10: validate + normalise
        ↓
OrchestratorService._parse_response()     ← attaches evidence/confidence (Task 9)
        ↓
CodeUnderstandingResponse (with confidence)
```

**Usage example (with a mock provider):**

```python
from app.orchestrator import OrchestratorService
from app.providers.base import LLMProvider, LLMRequest, LLMResponse

class MyProvider(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="The function adds two numbers.")

service = OrchestratorService(provider=MyProvider())
response = await service.analyse(request)  # CodeUnderstandingResponse
# response.confidence.level → ConfidenceLevel.CONFIRMED
```

---

## LLM Provider abstraction (`app/providers/`)

| Symbol           | Purpose                                                                              |
|------------------|--------------------------------------------------------------------------------------|
| `LLMProvider`    | Abstract base class; implement `async complete(request) -> LLMResponse`             |
| `LLMRequest`     | Provider-agnostic prompt: ordered `messages`, optional `temperature` and `max_tokens`|
| `LLMMessage`     | Single chat message with `role` (`system`/`user`/`assistant`) and `content`         |
| `LLMResponse`    | Provider-agnostic completion: `content`, optional `model` and `finish_reason`       |
| `ProviderError`  | Exception raised when the provider fails or is unreachable                          |
| `OllamaProvider` | Concrete provider calling a local Ollama server (`/api/chat`)                       |
| `MockProvider`   | Deterministic in-process mock for tests                                              |

---

## Running tests

```bash
cd apps/ai-engine
python -m pytest tests/ -q
```

Or from the repository root:

```bash
python -m pytest apps/ai-engine/tests -q
```

No real LLM service or vector database is required — all tests use in-process mocks.

### Performance tests

`tests/performance/` measures the engine's own cost with the model socket
stubbed, so inference time is excluded from every figure:

```bash
python -m pytest apps/ai-engine/tests/performance -q -s
```

`-s` prints each measurement as it is taken plus a summary table. The measured
results, thresholds, findings and NOT MEASURABLE items are documented in
[`docs/ai-performance-report.md`](./docs/ai-performance-report.md).

### Continuous integration

`.github/workflows/ai-engine.yml` runs the checks above automatically. It is
scoped to `apps/ai-engine/**` and is not a root repository workflow; the root
pipeline belongs to the CI/CD owners.

| Check | Command |
|---|---|
| Dependency install | `python -m pip install -r requirements.txt` |
| Import | `python -c "from app.main import app"` |
| Startup | build the ASGI app and call `/health` and `/ready` |
| Tests | `python -m pytest tests -q` |
| No live provider | the suite re-run with `PROVIDER_BASE_URL` pointed at an unroutable address |

It runs on Python 3.11 and 3.13 — 3.11 is the floor documented above and the
version `Dockerfile` ships; 3.13 is what contributors run locally.

The workflow needs **no Ollama, no model weights, no API credentials, and no
network access**. The last check enforces that rather than assuming it, so a
test that starts reaching for a real provider fails in CI instead of passing
here and breaking on a contributor's machine.

The root workflow can reuse this job instead of repeating these steps:

```yaml
jobs:
  ai-engine:
    uses: sigmaboy143/AI-Code-Understanding-Assistant/.github/workflows/ai-engine.yml@main
```

### Secrets

`.env.example` documents every supported variable and is the only `.env` file in
the repository; real `.env` files are git-ignored. `PROVIDER_API_KEY` is read
from the environment and never stored in the repository, and no API response
includes it.

---

## Specialised Agents (`app/agents/`)

These agents are focused analysis services.  They consume structured
repository-intelligence context that **must be supplied by the caller** (or an
upstream service/test fixture).  None of these agents scan the file system,
parse source code, call an LLM, or connect to external services.

> **Important:** The agents depend entirely on upstream repository intelligence.
> They do not discover modules, files, relationships, tests, or documentation
> on their own.

---

### Architecture Agent (`app/agents/architecture.py`)

**Purpose:** Explain system/module boundaries, major components, dependency
relationships, data flow, and entry points from supplied structured context.

**Required input — `ArchitectureContext`:**

| Field | Type | Description |
|---|---|---|
| `modules` | `list[ModuleInfo]` | Named modules/packages with optional descriptions |
| `files` | `list[str]` | Important file paths |
| `symbols` | `list[str]` | Key symbol names |
| `imports` | `list[str]` | Import statements/relationships |
| `relationships` | `list[RelationshipInfo]` | Dependency/call-graph edges (`source`, `target`, `kind`) |
| `services` | `list[ServiceInfo]` | Named services |
| `apis` | `list[str]` | API surface definitions |
| `documentation` | `str \| None` | Architecture documentation text |
| `entry_points` | `list[str]` | Known entry points |

**Output — `ArchitectureResult`:**
- `overview` — plain-language overview (from `documentation` if supplied; else derived from modules/services)
- `components` — identified components with `kind` (`module`, `service`, `file`, `entry_point`) and `ConfidenceLevel`
- `entry_points` — from `context.entry_points`
- `dependency_relationships` — from `context.relationships`
- `data_flow_summary` — rendered from relationships; `None` if none supplied
- `limitations` — what could not be determined
- `confidence` — `CONFIRMED` when context is supplied; `UNKNOWN` when empty

**Evidence behaviour:**
- `CONFIRMED`: component or relationship is directly present in the supplied context
- `UNKNOWN`: no context supplied for that aspect
- Evidence items reference only supplied fields (FILE source type for modules/services/files)
- `git_commit` evidence is never fabricated

**Limitations:**
- Does not scan the repository or parse code
- Does not infer undeclared dependencies
- Does not generate data-flow diagrams
- Cannot determine architecture aspects absent from the supplied context

**Usage:**

```python
from app.agents.architecture import ArchitectureAgent, ArchitectureContext, ModuleInfo, RelationshipInfo

agent = ArchitectureAgent()
ctx = ArchitectureContext(
    modules=[ModuleInfo(name="api", description="HTTP layer"), ModuleInfo(name="db")],
    relationships=[RelationshipInfo(source="api", target="db", kind="dependency")],
    entry_points=["src/main.py"],
)
result = agent.analyse(ctx)
# result.overview, result.components, result.dependency_relationships, result.confidence
```

---

### Documentation Agent (`app/agents/documentation.py`)

**Purpose:** Answer questions from supplied documentation.  The agent never
crawls the internet or invents undocumented behaviour.

**Required input — `DocumentationContext`:**

| Field | Type | Description |
|---|---|---|
| `readme` | `str \| None` | README content |
| `markdown_files` | `dict[str, str]` | `{filename: content}` Markdown documents |
| `docstrings` | `dict[str, str]` | `{symbol: docstring}` mapping |
| `api_docs` | `str \| None` | API documentation text |
| `architecture_notes` | `str \| None` | Architecture documentation text |
| `config_docs` | `str \| None` | Configuration documentation text |
| `question` | `str \| None` | Optional question to answer |

**Output — `DocumentationResult`:**
- `answer` — the answer from the supplied docs, or `"UNKNOWN: ..."` when docs don't answer
- `relevant_sections` — documentation sections that contributed to the answer
- `documented_facts` — facts explicitly stated in the supplied documentation
- `limitations` — what the agent cannot determine
- `confidence` — `CONFIRMED` when a matching source was found; `UNKNOWN` when not

**Evidence behaviour:**
- `CONFIRMED`: answer found in at least one supplied documentation source
- `UNKNOWN`: no documentation supplied, or question not answerable from docs
- Evidence source type is `DOCUMENTATION`
- No evidence is ever fabricated

**UNKNOWN behaviour:**
- Empty context → `"UNKNOWN: No documentation was supplied."`
- Question not found in any doc → `"UNKNOWN: The supplied documentation does not answer: '...'"`

**Limitations:**
- Keyword-based matching only; no semantic search
- Cannot answer questions about undocumented behaviour
- Does not crawl the internet or file system

**Usage:**

```python
from app.agents.documentation import DocumentationAgent, DocumentationContext

agent = DocumentationAgent()
ctx = DocumentationContext(
    readme="# MyProject\nA REST API for code analysis.",
    question="What is MyProject?",
)
result = agent.analyse(ctx)
# result.answer, result.confidence.level → ConfidenceLevel.CONFIRMED
```

---

### Test Agent (`app/agents/test_agent.py`)

**Purpose:** Explain what tests exist and what behaviour they verify, using
only the supplied test context.  The agent never runs a test parser, infers
coverage, or fabricates test behaviour.

**Required input — `SuiteContext`** (also exported as `TestContext`)**:**

| Field | Type | Description |
|---|---|---|
| `test_names` | `list[str]` | Test function/method names |
| `test_code` | `dict[str, str]` | `{test_name: source_code}` |
| `test_descriptions` | `dict[str, str]` | `{test_name: description}` |
| `target_symbol` | `str \| None` | Symbol under test |
| `target_file` | `str \| None` | File under test |
| `coverage_info` | `str \| None` | Supplied coverage information |
| `question` | `str \| None` | Optional question about tests |

**Output — `SuiteAnalysisResult`** (also exported as `TestResult`)**:**
- `overview` — summary of the test suite
- `tests` — per-test summaries (`name`, `description`, `has_code`, `confidence`)
- `target_symbol` / `target_file` — from the supplied context
- `coverage_summary` — from `coverage_info`; `"UNKNOWN: ..."` when not supplied
- `related_tests` — tests related to `target_symbol`/`target_file`
- `answer` — answer to the question; `"UNKNOWN: ..."` when unanswerable
- `limitations` — what was missing
- `confidence` — `CONFIRMED` when test context supplied; `UNKNOWN` when empty

**Evidence behaviour:**
- `CONFIRMED`: test names/code/descriptions directly supplied
- `UNKNOWN`: no test context provided
- Evidence source type is `TEST`
- Coverage is `UNKNOWN` unless `coverage_info` is explicitly supplied

**Limitations:**
- Does not run tests or measure coverage
- Does not parse test code to extract assertions
- Cannot explain why a test exists unless a description is supplied

**Usage:**

```python
from app.agents.test_agent import TestAgent, SuiteContext as TestContext

agent = TestAgent()
ctx = TestContext(
    test_names=["test_login_success", "test_login_failure"],
    test_descriptions={"test_login_success": "Verifies valid credentials succeed."},
    target_symbol="login",
    coverage_info="82% line coverage",
)
result = agent.analyse(ctx)
# result.overview, result.tests, result.related_tests, result.coverage_summary
```

---

### Repository Onboarding Agent (`app/agents/onboarding.py`)

**Purpose:** Generate a structured onboarding guide for a developer who is
unfamiliar with the repository.  Uses only the supplied repository-intelligence
context; never invents project purpose, architecture, workflows, or deployment
processes.

**Required input — `OnboardingContext`:**

| Field | Type | Description |
|---|---|---|
| `project_name` | `str \| None` | Project/repository name |
| `project_description` | `str \| None` | Short description of the project |
| `language` | `str \| None` | Primary programming language |
| `modules` | `list[str]` | Named modules/packages |
| `files` | `list[str]` | Important file paths |
| `entry_points` | `list[str]` | Known entry points |
| `documentation` | `str \| None` | Documentation text (README, wiki, etc.) |
| `tests` | `list[str]` | Test names or test file paths |
| `development_commands` | `dict[str, str]` | Known commands (e.g. `{"test": "pytest"}`) |
| `dependencies` | `list[str]` | Known external dependencies |

**Output — `OnboardingResult`:**
- `project_overview` — from `project_name` + `project_description` + `language`; falls back to `documentation` excerpt; `UNKNOWN` when absent
- `entry_points` — from `context.entry_points`
- `major_components` — from `context.modules`
- `important_files` — from `context.files`
- `development_flow` — from `context.development_commands`; `UNKNOWN` when not supplied
- `documentation_references` — from `context.documentation`
- `test_references` — from `context.tests`
- `suggested_starting_points` — derived from supplied context
- `sections` — all eight onboarding sections with `ConfidenceLevel` annotations
- `limitations` — missing aspects explicitly noted
- `confidence` — `CONFIRMED` when any context supplied; `UNKNOWN` when empty

**Evidence behaviour:**
- `CONFIRMED`: fact directly supplied in context
- `UNKNOWN`: required information absent
- Evidence items reference supplied files, documentation, tests, and commands
- No evidence is ever fabricated

**UNKNOWN behaviour:**
- Absent field → corresponding section has `confidence = ConfidenceLevel.UNKNOWN`
- Each limitation is explicitly recorded in `result.limitations`

**Limitations:**
- Does not scan the file system
- Does not infer project purpose beyond what is supplied
- Suggested starting points are derived solely from supplied context
- Cannot determine deployment process unless explicitly supplied

**Usage:**

```python
from app.agents.onboarding import OnboardingAgent, OnboardingContext

agent = OnboardingAgent()
ctx = OnboardingContext(
    project_name="CodeAnalyser",
    project_description="A REST API for automated code analysis.",
    language="Python",
    modules=["api", "db"],
    entry_points=["src/main.py"],
    development_commands={"test": "pytest tests/", "lint": "ruff check ."},
)
result = agent.onboard(ctx)
# result.project_overview, result.suggested_starting_points, result.sections
```

---

---

### Code Explanation Agent (`app/agents/explanation.py`)

**Purpose:** Explain submitted source code using only the supplied code, retrieved
context chunks, and optional supplementary context.  The agent answers the user's
question, describes visible control/data flow, and summarises what the code does.

**Required input — `ExplanationContext`:**

| Field | Type | Description |
|---|---|---|
| `source_code` | `str` | The source code to explain (required) |
| `language` | `ProgrammingLanguage` | Language label |
| `file_path` | `str \| None` | Optional repository-relative path |
| `question` | `str \| None` | Optional question to answer |
| `analyses` | `list[AnalysisType]` | Optional analysis-type hints |
| `retrieved_chunks` | `list[IncludedChunk]` | Pre-selected context chunks |
| `user_context` | `str \| None` | Optional supplementary context text |

**Output — `ExplanationResult`:**
- `overview` — high-level description of what the code does
- `details` — longer walkthrough (from LLM response, when longer than overview)
- `flow_steps` — visible control/data flow steps detected in the code
- `question_answer` — answer to the supplied question; `"UNKNOWN: ..."` when unanswerable
- `limitations` — what the agent cannot determine from the supplied context
- `confidence` — `CONFIRMED` when source code is supplied; `UNKNOWN` when code is empty

**Evidence behaviour:**
- `CONFIRMED`: source code and/or retrieved chunks are supplied
- `UNKNOWN`: source code is empty/blank
- Evidence items reference submitted source code and retrieved chunks
- No Git evidence is ever fabricated

**Flow step extraction:**
- Detects `def`, `class`, `return`, `raise`, `if`/`elif`, `for`/`while` at the visible
  source level using simple line heuristics (no AST)
- Only constructs visibly present in the supplied code are described
- Capped at 20 steps

**LLM provider:**
- When a provider is injected: `overview`, `details`, and `question_answer` are drawn
  from the LLM completion
- When no provider is injected: deterministic fallback using code line count and language
- Tests use `MockProvider` — no real LLM is called

**Limitations:**
- Does not scan the repository or build a dependency graph
- Does not run the code or execute tests
- No AST parsing is performed
- Claims are not individually mapped to evidence items (free-text LLM response)
- Control/data flow is described textually from the visible code surface only

**Usage:**

```python
from app.agents.explanation import ExplanationAgent, ExplanationContext
from app.providers.mock import MockProvider
from app.schemas.code_understanding import ProgrammingLanguage

agent = ExplanationAgent(provider=MockProvider(response_text="Adds two numbers."))
ctx = ExplanationContext(
    source_code="def add(a, b):\n    return a + b",
    language=ProgrammingLanguage.PYTHON,
    file_path="src/math.py",
    question="What does add() return?",
)
result = await agent.explain(ctx)
# result.overview, result.flow_steps, result.question_answer, result.confidence
```

---

### WHY / Git Reasoning Agent (`app/agents/git_reasoning.py`)

**Purpose:** Explain documented reasons for a code change using ONLY the Git context
that is explicitly supplied.  The agent never fabricates commits, authors, dates,
PRs, issues, or historical events.

> **Important:** Git context is supplied externally.  The agent performs no Git
> operations and does not scan the repository.

**Required input — `GitContext`:**

| Field | Type | Description |
|---|---|---|
| `commit_hash` | `str \| None` | Commit SHA (informational only) |
| `commit_message` | `str \| None` | Commit message text |
| `diff` | `str \| None` | Raw diff text |
| `changed_files` | `list[str]` | Changed file paths |
| `issue_text` | `str \| None` | Linked issue description |
| `pr_text` | `str \| None` | Linked PR description |
| `code_before` | `str \| None` | Code before the change |
| `code_after` | `str \| None` | Code after the change |
| `related_context` | `str \| None` | Other relevant context text |

**Output — `GitReasoningResult`:**
- `why_summary` — why the change was made; `"UNKNOWN: ..."` when undeterminable
- `documented_reasons` — reasons directly stated in commit message, PR, or issue
- `inferred_reasons` — reasons inferred from diff or code structure
- `reasoning_chain` — ordered steps with source attribution and confidence level
- `limitations` — what the agent cannot determine from the supplied context
- `confidence` — `CONFIRMED` / `INFERRED` / `UNKNOWN` (see rules below)

**Confidence rules:**

| Situation | Level |
|---|---|
| Reason directly stated in commit message / PR / issue | `CONFIRMED` |
| Reason reasoned from diff or code change (not explicitly stated) | `INFERRED` |
| No useful context supplied | `UNKNOWN` |

**Evidence behaviour:**
- `GIT_COMMIT` source type for commit message, issue, and PR evidence
- `SOURCE_CODE` source type for diff and code-change evidence
- `FILE` source type for changed-file evidence
- No evidence is ever fabricated — only supplied fields generate evidence items

**NEVER fabricates:**
- Commit hashes, authors, or dates
- PR or issue numbers or titles beyond what is supplied
- Author motives or historical events

**Limitations:**
- Git context must be supplied externally; no Git parsing or repository scanning
- Only the most recent supplied context is analysed; multi-commit history is not
  reconstructed
- Inferences are structural (line counts, diff patterns); no semantic understanding
  of intent beyond keywords visible in the diff

**Usage:**

```python
from app.agents.git_reasoning import GitReasoningAgent, GitContext

agent = GitReasoningAgent()
ctx = GitContext(
    commit_message="Fix: handle None input in process()",
    diff="- if value:\n+ if value is not None:",
    issue_text="Null pointer error when value is falsy but not None.",
)
result = agent.analyse(ctx)
# result.why_summary, result.documented_reasons, result.confidence.level
```

---

### Debug Agent (`app/agents/debug_impact.py` — `DebugAgent`)

**Purpose:** Identify the likely failure location and root cause of an error using
only the supplied error message, stack trace, source code, and retrieved context.

**Required input — `DebugContext`:**

| Field | Type | Description |
|---|---|---|
| `error_message` | `str` | The error/exception message (required) |
| `stack_trace` | `str \| None` | Full stack trace text |
| `source_code` | `str \| None` | Relevant source code |
| `retrieved_chunks` | `list[IncludedChunk]` | Retrieved context chunks |
| `recent_changes` | `str \| None` | Optional recent-change description |
| `file_path` | `str \| None` | Repository-relative path |

**Flow:**
```
Error message
    ↓
Stack trace / source code / retrieved chunks
    ↓
Evidence
    ↓
Root cause reasoning
    ↓
DebugResult
```

**Output — `DebugResult`:**
- `error_summary` — truncated error message (≤ 200 chars)
- `likely_locations` — failure locations extracted from the stack trace
- `root_cause` — likely root cause; `"UNKNOWN: ..."` when evidence is insufficient
- `investigation_steps` — suggested next investigation/fix direction
- `limitations` — what the agent cannot determine
- `confidence` — `CONFIRMED` (stack+code), `INFERRED` (partial), `UNKNOWN` (message only)

**Evidence and confidence behaviour:**

| Supplied | Confidence |
|---|---|
| Stack trace + source code | `CONFIRMED` |
| Stack trace only or source code only | `INFERRED` |
| Error message only | `UNKNOWN` |

**Common error heuristics (deterministic, no LLM):**
- `AttributeError` → suggests None dereference
- `TypeError` → suggests type mismatch
- `KeyError` → suggests missing dict key
- `IndexError` → suggests list out of range
- `ImportError` / `ModuleNotFoundError` → suggests missing module
- `ValueError` → suggests invalid argument
- `NameError` → suggests undefined variable

**Limitations:**
- Does not execute code or reproduce the error
- Stack-trace location extraction uses Python-style frame parsing only
- No AST analysis is performed
- Root cause inference is heuristic when no LLM provider is injected

**Usage:**

```python
from app.agents.debug_impact import DebugAgent, DebugContext
from app.providers.mock import MockProvider

agent = DebugAgent(provider=MockProvider(response_text="The value is None."))
ctx = DebugContext(
    error_message="AttributeError: 'NoneType' object has no attribute 'strip'",
    stack_trace='  File "src/processor.py", line 42, in process\n    result = value.strip()',
    source_code="def process(value):\n    result = value.strip()\n    return result",
)
result = await agent.analyse(ctx)
# result.likely_locations, result.root_cause, result.investigation_steps, result.confidence
```

---

### Impact Analysis Agent (`app/agents/debug_impact.py` — `ImpactAgent`)

**Purpose:** Identify directly and indirectly affected components when code changes,
using only the supplied dependency/relationship context and test context.

> **Important:** Dependency relationships are supplied externally.  The agent does
> not parse source code or build a dependency graph.

**Required input — `ImpactContext`:**

| Field | Type | Description |
|---|---|---|
| `changed_component` | `str` | Name of the changed component (required) |
| `changed_code` | `str \| None` | The changed source code |
| `relationships` | `list[ComponentRelationship]` | Supplied dependency relationships |
| `test_names` | `list[str]` | Supplied test names |
| `test_file_paths` | `list[str]` | Supplied test file paths |

**`ComponentRelationship` fields:** `source`, `target`, `kind`, `description`

**Output — `ImpactResult`:**
- `changed_component` — the changed component name
- `directly_affected` — components with a direct dependency on the changed component
- `indirectly_affected` — components one transitive hop away (INFERRED)
- `related_tests` — from supplied `test_names` or `test_file_paths`
- `impact_summary` — plain-language summary; `"UNKNOWN: ..."` when no relationships
- `limitations` — what the agent cannot determine
- `confidence` — `CONFIRMED` (relationships supplied), `INFERRED` (tests only), `UNKNOWN` (nothing)

**Evidence and confidence behaviour:**

| Supplied | Confidence |
|---|---|
| Relationships | `CONFIRMED` (direct); `INFERRED` (indirect) |
| Tests only (no relationships) | `INFERRED` |
| Nothing | `UNKNOWN` |

**Limitations:**
- Does not build a dependency parser or scan the repository
- Only one level of transitive relationships is explored (direct dependants of
  direct dependants)
- Deeper transitive chains are not analysed because the supplied data may be incomplete
- If `relationships` is empty, both `directly_affected` and `indirectly_affected` are
  always empty — impact is `UNKNOWN`

**Usage:**

```python
from app.agents.debug_impact import ImpactAgent, ImpactContext, ComponentRelationship

agent = ImpactAgent()
ctx = ImpactContext(
    changed_component="UserService",
    relationships=[
        ComponentRelationship(source="AuthController", target="UserService"),
        ComponentRelationship(source="OrderService", target="UserService"),
    ],
    test_names=["test_create_user", "test_delete_user"],
)
result = agent.analyse(ctx)
# result.directly_affected, result.indirectly_affected, result.related_tests
```

---

## Current limitations

- **Only Ollama** is supported as a provider (`PROVIDER=ollama`).
- **Free-text summary only** — structured response fields (`explanation`, `structure`,
  `dependencies`, `improvements`) are defined in the schema but not yet populated
  by the response parser.
- **No production RAG** — retrieval uses in-memory keyword matching only.
- **No LLM confidence scoring** — confidence is derived from the presence of
  retrieved chunks or submitted source code, not from any model self-assessment.
- **No numeric confidence score** — there is no real calculation to back one up.
- **Git context is supplied externally** — the WHY/Git Reasoning Agent does not
  perform any Git operations.  Callers must supply `commit_message`, `diff`,
  `issue_text`, `pr_text`, or `code_before`/`code_after` explicitly.
- **Dependency relationships are supplied externally** — the Impact Analysis Agent
  does not parse source code or build a dependency graph.  Callers must supply
  `ComponentRelationship` objects.
- **Unsupported information becomes UNKNOWN** — when the required context is absent
  the agents return `"UNKNOWN"` rather than fabricating data.
- **No repository or Git scanning** — none of the agents (Explanation, Git Reasoning,
  Debug, or Impact) scan the file system, run Git commands, or parse code beyond
  simple line-level heuristics.
- **No automatic test evidence** — the Test Agent consumes supplied test context only;
  it does not discover or parse tests from the file system.
- **Context builder** — `extra_sections` is always empty; Git, test, and architecture
  context are extension points for future milestones.
- **Agents require upstream intelligence** — Architecture, Documentation, Test,
  Onboarding, Explanation, Git Reasoning, Debug, and Impact agents consume
  pre-supplied context; they do not scan repositories themselves.
  An upstream repository-intelligence service must supply the structured context.
- **No embedding service** — semantic/vector search is not implemented.
- **Documentation Agent uses keyword matching** — question answering is keyword-based,
  not semantic; complex or indirect questions may not be answered correctly.
- **Explanation Agent flow steps** — control/data flow detection uses line-level
  heuristics only; complex patterns (nested closures, generators, decorators) may
  not be fully captured.
- **Debug Agent stack trace parsing** — designed for Python-style tracebacks;
  other languages' stack trace formats may not be fully parsed.
