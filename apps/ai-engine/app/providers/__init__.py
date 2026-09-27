"""LLM provider abstraction for the AI Engine.

All concrete providers (Ollama, OpenAI, etc.) must implement ``LLMProvider``.
The orchestrator depends only on this interface — it never imports a concrete
provider class.
"""

from .base import LLMMessage, LLMProvider, LLMRequest, LLMResponse, ProviderError

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderError",
]
