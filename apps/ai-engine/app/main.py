from fastapi import FastAPI

app = FastAPI(
    title="AI Engine",
    description="AI Engine foundation for code understanding, RAG, and reasoning.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
