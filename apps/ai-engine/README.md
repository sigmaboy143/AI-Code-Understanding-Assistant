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

## Running tests

```bash
pytest tests/
```
