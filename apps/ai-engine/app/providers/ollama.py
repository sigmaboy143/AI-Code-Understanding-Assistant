"""Ollama LLM provider.

Sends chat-completion requests to a local Ollama server using its
``/api/chat`` endpoint.  The HTTP call is made with ``httpx`` so it runs
on the same asyncio event loop as FastAPI.

Environment variables consumed
------------------------------
PROVIDER_BASE_URL   Base URL of the Ollama server (default: http://localhost:11434)
MODEL               Model name to use (default: llama3)
REQUEST_TIMEOUT     Seconds before the HTTP request times out (default: 60)
"""

from __future__ import annotations

import asyncio

import httpx

from app.providers.base import LLMProvider, LLMRequest, LLMResponse, ProviderError


class OllamaProvider(LLMProvider):
    """Concrete LLM provider that calls a local Ollama server.

    Parameters
    ----------
    base_url:
        Root URL of the Ollama server, e.g. ``http://localhost:11434``.
    model:
        Ollama model tag, e.g. ``llama3``, ``codellama``.
    timeout:
        Seconds to wait for the HTTP response.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send *request* to the Ollama chat endpoint and return the response.

        Raises
        ------
        ProviderError
            On connection errors, unexpected HTTP status codes, parse failures,
            or timeouts.
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": m.role, "content": m.content} for m in request.messages
            ],
            "stream": False,
        }
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}

        url = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
        except asyncio.TimeoutError as exc:
            raise ProviderError(
                f"Ollama request timed out after {self._timeout}s", provider="ollama"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Ollama request timed out after {self._timeout}s", provider="ollama"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to Ollama at {self._base_url}", provider="ollama"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"Ollama HTTP request failed: {exc}", provider="ollama"
            ) from exc

        if resp.status_code != 200:
            raise ProviderError(
                f"Ollama returned HTTP {resp.status_code}", provider="ollama"
            )

        try:
            data = resp.json()
            content: str = data["message"]["content"]
        except (KeyError, ValueError) as exc:
            raise ProviderError(
                f"Ollama response parse error: {exc}", provider="ollama"
            ) from exc

        return LLMResponse(
            content=content,
            model=data.get("model"),
            finish_reason=data.get("done_reason"),
        )
