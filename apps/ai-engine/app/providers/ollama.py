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

        Generation parameters are translated into Ollama's ``options`` object:

        - ``LLMRequest.temperature`` → ``options.temperature``
        - ``LLMRequest.max_tokens``   → ``options.num_predict``

        ``options`` is omitted entirely when neither is set, so the server
        default applies rather than a value invented here.

        Separately, ``"think": False`` is sent for ``qwen3`` tags so the model's
        reasoning trace is not generated.  The trace is drawn from the same
        budget as the answer, so leaving it enabled makes the ``num_predict``
        cap insufficient on its own; see the comment at the payload build.  No
        other model tag is affected.

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

        options: dict[str, float | int] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        # ``max_tokens`` is Ollama's ``options.num_predict``.  Sending it is what
        # bounds the completion: with ``stream: False`` the response body is not
        # written until generation ends, so an uncapped thinking model can run
        # past the read timeout and surface as a 504 (Phase 13).
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options

        # ``qwen3`` is a reasoning model: it emits a ``thinking`` trace before the
        # answer, and those tokens are drawn from the *same* generation budget as
        # the answer.  Capping ``num_predict`` while leaving thinking on therefore
        # spends most of the cap on the trace, and the five-analysis prompt can
        # still outlast the read timeout (Phase 13).  Suppressing the trace is
        # what makes the cap sufficient, so it is sent for the tags measured to
        # need it and for no others — a model this was never measured against
        # keeps whatever behaviour it already had.
        if self._model.lower().startswith("qwen3"):
            payload["think"] = False

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

        # Thinking models (``qwen3``) split the reply in two: ``message.thinking``
        # carries the reasoning trace and ``message.content`` carries the answer.
        # Only ``message.content`` is read, so the trace is discarded rather than
        # prepended to the summary.  A trace left with no room for an answer
        # yields an empty ``content``; that is returned unchanged so the output
        # validation pipeline — not this transport layer — decides the
        # documented fallback.  Nothing here invents content.
        return LLMResponse(
            content=content,
            model=data.get("model"),
            finish_reason=data.get("done_reason"),
        )
