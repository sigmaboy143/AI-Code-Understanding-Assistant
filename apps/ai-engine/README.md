# AI Engine

The AI Engine is the core intelligence layer of the AI-Code-Understanding-Assistant project.
It is responsible for:

- Code analysis and understanding
- Retrieval-Augmented Generation (RAG) over codebases
- AI agent orchestration and reasoning
- Evidence collection and confidence scoring

The service is implemented with **Python** and **FastAPI** and is designed to be modular so that
capabilities (embeddings, vector stores, LLM providers, agents) can be added incrementally.

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

## LLM provider abstraction

`app/providers/` is the single, provider-independent entry point for talking to a
large language model. It defines the contract that every concrete provider
implements, plus the neutral data types that cross that boundary.

```python
from app.providers import LLMRequest, Message, MessageRole

request = LLMRequest(
    messages=[Message(role=MessageRole.USER, content="Summarise this module.")],
)
response = await provider.generate(request)
print(response.text)
```

**What it provides**

- `LLMProvider` — abstract async interface. A provider reports its
  `provider_name` and default `model`, and implements
  `async generate(request) -> LLMResponse`.
- `LLMRequest` / `Message` / `MessageRole` — chat input: a non-empty list of
  role-tagged messages, an optional per-request `model` override, and optional
  `GenerationOptions` (`temperature`, `max_tokens`, `top_p`, `stop`).
- `LLMResponse` — generated output as a typed value: `text`, `model`,
  `provider`, `finish_reason`, `usage`, plus an opaque `raw` payload kept for
  debugging only.
- `ProviderError` and its subclasses — `ProviderConfigurationError`,
  `ProviderTimeoutError`, `ProviderRateLimitError`, `ProviderResponseError`.
  Every failure a provider can produce is translated into one of these, so
  callers handle error *kinds* rather than vendor payloads.

**Why agents should use it**

Agents and application code import from `app.providers` and never from a
concrete provider. Because the contract is provider-neutral, an agent can be
written, tested and reasoned about without any knowledge of which vendor is
serving the request, and swapping vendors does not touch agent code. Because
failures arrive as `ProviderError` subclasses, agents get uniform, predictable
error handling.

**Adding a provider**

Concrete providers are added *behind* the interface — implement `LLMProvider`,
translate the vendor's wire format into the neutral types, and translate its
errors into `ProviderError` subclasses. Nothing in the abstraction changes, and
no calling code needs to be modified. The bundled `MockLLMProvider` in
`app/providers/mock.py` is the reference implementation: it is deterministic,
performs no I/O and needs no credentials, so it backs local development and the
unit tests without contacting any LLM service.

---

## Running tests

```bash
pytest tests/
```
