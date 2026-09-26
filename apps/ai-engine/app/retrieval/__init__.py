"""Retrieval / RAG foundation for the AI Engine.

Public API
----------
- ``RetrievedChunk``   — typed unit of retrieved context
- ``RetrieverBase``    — abstract retriever interface
- ``InMemoryRetriever``— deterministic in-memory/lexical retriever

Usage::

    from app.retrieval import InMemoryRetriever, RetrievedChunk

    corpus = [
        RetrievedChunk(
            chunk_id="1",
            file_path="src/auth.py",
            content="def login(user, password): ...",
        )
    ]
    retriever = InMemoryRetriever(corpus)
    chunks = retriever.retrieve("user authentication", top_k=5)
"""

from .base import RetrieverBase, RetrievedChunk
from .memory import InMemoryRetriever

__all__ = ["InMemoryRetriever", "RetrievedChunk", "RetrieverBase"]
