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

```bash
cp .env.example .env
# Edit .env and fill in any values you need
```

---

## Running the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at <http://localhost:8000>.

Interactive docs (Swagger UI): <http://localhost:8000/docs>

---

## Provider configuration

All settings are read from environment variables (or a `.env` file).
No credentials are hard-coded anywhere.

| Variable           | Default                    | Description                                                           |
|--------------------|----------------------------|-----------------------------------------------------------------------|
| `HOST`             | `0.0.0.0`                  | Network interface to bind                                             |
| `PORT`             | `8000`                     | TCP port                                                              |
| `PROVIDER`         | `ollama`                   | LLM provider: `ollama` (only supported value currently)              |
| `MODEL`            | `llama3`                   | Model name forwarded to the provider                                  |
| `PROVIDER_BASE_URL`| `http://localhost:11434`   | Base URL for self-hosted providers (Ollama)                           |
| `REQUEST_TIMEOUT`  | `60`                       | Seconds to wait for a provider response before raising a 504 error   |
| `PROVIDER_API_KEY` | *(not set)*                | API key for cloud providers (OpenAI, Anthropic). Not used for Ollama |

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

No real LLM service or vector database is required — all tests use in-process mocks.

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
- **No automatic Git reasoning** — Git history, commits, and PRs are not inferred;
  `git_commit` evidence type is reserved but never auto-populated.
- **No automatic test evidence** — `test` evidence type is reserved but never auto-populated.
- **Context builder** — `extra_sections` is always empty; Git, test, and architecture
  context are extension points for future milestones.
- **No specialised agents** — single-turn LLM call only.
- **No embedding service** — semantic/vector search is not implemented.
