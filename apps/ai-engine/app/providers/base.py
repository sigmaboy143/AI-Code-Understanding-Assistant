"""Abstract LLM provider interface.

Concrete provider implementations (Ollama, OpenAI, …) live outside this file.
The orchestrator imports only from this module so that switching providers
requires no changes to orchestration logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderError(Exception):
    """Raised when the LLM provider returns an error or is unreachable.

    Attributes
    ----------
    message:
        Human-readable description of the failure.
    provider:
        Name of the provider that failed, if known.
    """

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class LLMMessage(BaseModel):
    """A single message in a chat-style prompt."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"] = Field(
        description="Sender role: 'system', 'user', or 'assistant'."
    )
    content: str = Field(description="Text content of the message.")


class LLMRequest(BaseModel):
    """Provider-agnostic request sent to an LLM.

    The orchestrator populates this from a ``CodeUnderstandingRequest``;
    the concrete provider translates it to its own API format.
    """

    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage] = Field(
        min_length=1,
        description="Ordered list of messages forming the prompt.",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature; None means use the provider default.",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of tokens in the completion.",
    )


class LLMResponse(BaseModel):
    """Provider-agnostic response returned by an LLM.

    Concrete providers translate their API responses into this model before
    returning them to the orchestrator.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Text of the completion produced by the model.")
    model: str | None = Field(
        default=None, description="Name of the model that produced the response."
    )
    finish_reason: str | None = Field(
        default=None,
        description="Reason the model stopped generating tokens, e.g. 'stop'.",
    )


class LLMProvider(ABC):
    """Interface that every concrete LLM provider must implement.

    The orchestrator depends on this abstract class only.  Callers inject a
    concrete implementation at construction time.

    Example usage::

        provider: LLMProvider = OllamaProvider(...)
        service = OrchestratorService(provider=provider)
        response = await service.analyse(request)
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send *request* to the LLM and return the completion.

        Parameters
        ----------
        request:
            The prompt messages and optional generation parameters.

        Returns
        -------
        LLMResponse
            The model's response.

        Raises
        ------
        ProviderError
            If the provider is unreachable, returns an error status, or the
            response cannot be parsed.
        """
