"""AI Orchestrator — coordinates code-understanding requests with an LLM provider.

The orchestrator is the only layer that knows how a ``CodeUnderstandingRequest``
maps to an ``LLMRequest`` and how an ``LLMResponse`` maps back to a
``CodeUnderstandingResponse``.  It is intentionally thin: no RAG, no agents,
no AST parsing.  Those capabilities can be layered in later by enriching the
prompt-building step or the result-parsing step.
"""

from .service import OrchestratorService

__all__ = ["OrchestratorService"]
