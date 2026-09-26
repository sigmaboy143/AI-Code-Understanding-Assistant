# AI Engine

The AI Engine is the core intelligence layer of the AI-Code-Understanding-Assistant project.
It is responsible for:

- Code analysis and understanding via an LLM provider abstraction
- Provider-agnostic orchestration of code-understanding requests

The service is implemented with **Python** and **FastAPI** and is designed to be modular so that
capabilities (embeddings, vector stores, specialised agents) can be added incrementally.

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

## Health endpoint

| Method | Path      | Description          |
|--------|-----------|----------------------|
| GET    | `/health` | Returns service status |

**Example response**

```json
{"status": "ok"}
```

---

## API schemas

Typed Pydantic schemas for the Code Understanding API live in
`app/schemas/code_understanding.py`. They define the request/response contract only —
no LLM, RAG, embedding, or AST logic is implemented yet, and no field is tied to a
specific model provider.

| Schema                          | Purpose                                                       |
|---------------------------------|---------------------------------------------------------------|
| `CodeUnderstandingRequest`      | Submits `source_code`, `language`, optional `file_path`, `question`, `context`, `analyses` |
| `CodeUnderstandingResponse`     | Result: `summary` plus optional explanation, error, structure, dependency, and improvement sections |
| `AnalysisMetadata`              | Language, path, analyses performed, and confidence of a result |
| `ProgrammingLanguage`, `AnalysisType`, `Severity`, `DependencyKind` | Closed string enums used across the contract |

---

## LLM Provider abstraction (`app/providers/`)

All LLM providers implement the abstract `LLMProvider` interface defined in
`app/providers/base.py`. The orchestrator depends only on this interface — no
concrete provider (Ollama, OpenAI, etc.) is referenced in orchestration code.

| Symbol         | Purpose                                                                              |
|----------------|--------------------------------------------------------------------------------------|
| `LLMProvider`  | Abstract base class; concrete providers implement `async complete(request) -> LLMResponse` |
| `LLMRequest`   | Provider-agnostic prompt: ordered `messages`, optional `temperature` and `max_tokens` |
| `LLMMessage`   | Single chat message with `role` (`system`/`user`/`assistant`) and `content`         |
| `LLMResponse`  | Provider-agnostic completion: `content`, optional `model` and `finish_reason`       |
| `ProviderError`| Exception raised when the provider fails or is unreachable                          |

---

## AI Orchestrator (`app/orchestrator/`)

`OrchestratorService` coordinates a code-understanding request end-to-end:

```
CodeUnderstandingRequest
        ↓
OrchestratorService._build_llm_request()   ← constructs system + user messages
        ↓
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

**Design decisions:**

- Prompt construction (`_build_llm_request` / `_build_messages`) is isolated so
  future components (RAG context, evidence, agents) can enrich the prompt without
  changing `analyse()`.
- Response parsing (`_parse_response`) is isolated so structured extraction or
  confidence scoring can be added later.
- `ProviderError` propagates unchanged — no double-wrapping.
- No concrete provider is shipped in this package; tests use a deterministic mock.

---

## Running tests

```bash
cd apps/ai-engine
python -m pytest tests/ -q
```

No real LLM service is required — all orchestrator tests use an in-process mock.
