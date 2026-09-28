"""Context builder package (Task 8).

Centralised context-assembly layer that sits between the retrieval layer
and the reasoning / orchestrator pipeline.

Public API
----------
- ``BuiltContext``       — typed model representing the assembled context
- ``ContextBuilder``     — stateless builder; call ``build()`` to assemble
- ``MAX_CONTEXT_CHARS``  — default hard cap on total assembled context size
"""

from app.context_builder.builder import (
    MAX_CONTEXT_CHARS,
    BuiltContext,
    ContextBuilder,
)

__all__ = [
    "BuiltContext",
    "ContextBuilder",
    "MAX_CONTEXT_CHARS",
]
