"""Deterministic mock LLM provider for testing.

Import this instead of a real provider in tests so no network access is needed.
The mock records every request and returns a fixed response text.
"""

from __future__ import annotations

from app.providers.base import LLMProvider, LLMRequest, LLMResponse


class MockProvider(LLMProvider):
    """Deterministic in-process mock provider.

    Parameters
    ----------
    response_text:
        The fixed text returned as the LLM completion.

    Attributes
    ----------
    calls:
        List of all ``LLMRequest`` objects received so far.
    """

    def __init__(self, response_text: str = "Mock analysis result.") -> None:
        self.response_text = response_text
        self.calls: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(content=self.response_text)
