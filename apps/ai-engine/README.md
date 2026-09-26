# AI Engine

The AI Engine is the core intelligence layer of the AI-Code-Understanding-Assistant project.
It provides:

- A FastAPI HTTP service for code understanding via an LLM provider abstraction
- A grounded reasoning layer that constructs analysis-aware, anti-fabrication prompts
- A provider-independent retrieval foundation (lexical in-memory retriever)

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

| Field               | Type                      | Always present | Description                                       |
|---------------------|---------------------------|----------------|---------------------------------------------------|
| `summary`           | `string`                  | ✅             | Overall plain-language summary (from LLM output)  |
| `explanation`       | `CodeExplanation \| null` | ❌             | Detailed code explanation (not populated currently)|
| `error_explanation` | `ErrorExplanation \| null`| ❌             | Error/bug explanation (not populated currently)    |
| `structure`         | `StructureAnalysis \| null`| ❌            | Structural outline (not populated currently)       |
| `dependencies`      | `DependencyAnalysis \| null`| ❌           | Dependency analysis (not populated currently)      |
| `improvements`      | `ImprovementSuggestion[]` | ✅ (empty)     | Improvement suggestions (not populated currently)  |
| `metadata`          | `AnalysisMetadata`        | ✅             | Language, file path, analyses performed            |

> **Note:** Currently the LLM's free-text completion is placed into `summary`.
> The optional structured fields (`explanation`, `structure`, `dependencies`, `improvements`)
> are schema-ready but are not populated by the current response parser — they require
> structured extraction to be added to `_parse_response` in a future task.

**Example response**
```json
{
  "summary": "The add function takes two arguments and returns their sum. ...",
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
- No confidence scoring.
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
OrchestratorService._build_llm_request()   ← delegates to app.reasoning
        ↓                                     (RAG chunks injected here)
LLMProvider.complete()                     ← provider-agnostic call
        ↓
OrchestratorService._parse_response()      ← maps LLMResponse → CodeUnderstandingResponse
        ↓
CodeUnderstandingResponse
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
- **No confidence scoring** — `metadata.confidence` is always `null`.
- **No Git reasoning** — Git history, commits, and PRs are not inferred.
- **No specialised agents** — single-turn LLM call only.
- **No embedding service** — semantic/vector search is not implemented.
