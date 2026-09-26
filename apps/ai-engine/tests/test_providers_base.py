"""Contract tests for the provider abstraction itself."""

import asyncio
import importlib
import socket

import pytest

from app.providers import (
    GenerationOptions,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.mock import MockLLMProvider


class MinimalProvider(LLMProvider):
    """Third-party style provider: only the interface is implemented here."""

    def __init__(self) -> None:
        self._provider_name = "minimal"
        self._model = "minimal-1"

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=request.messages[-1].content.upper(),
            model=self.resolve_model(request),
            provider=self.provider_name,
        )


class ExplodingProvider(MinimalProvider):
    """Provider that fails, to check error translation."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise self._error


def user_request(text: str = "hello") -> LLMRequest:
    return LLMRequest(messages=[Message(role=MessageRole.USER, content=text)])


def test_provider_package_is_importable():
    package = importlib.import_module("app.providers")
    for name in package.__all__:
        assert hasattr(package, name), f"app.providers.{name} is not exported"


def test_base_module_exposes_the_interface():
    base = importlib.import_module("app.providers.base")
    assert base.LLMProvider is LLMProvider
    assert base.LLMRequest is LLMRequest
    assert base.LLMResponse is LLMResponse
    assert set(LLMProvider.__abstractmethods__) == {
        "provider_name",
        "model",
        "generate",
    }


def test_llm_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_concrete_provider_can_satisfy_the_abstraction():
    provider = MinimalProvider()

    assert isinstance(provider, LLMProvider)
    assert provider.provider_name == "minimal"
    assert provider.model == "minimal-1"


def test_generate_is_declared_async_on_the_interface():
    assert asyncio.iscoroutinefunction(LLMProvider.generate)


def test_resolve_model_prefers_request_override_then_default():
    provider = MinimalProvider()

    assert provider.resolve_model(user_request()) == "minimal-1"
    assert provider.resolve_model(LLMRequest(messages=user_request().messages, model="other")) == "other"


def test_request_accepts_plain_dicts_and_validates_input():
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

    assert request.messages[0] == Message(role=MessageRole.USER, content="hi")
    assert request.options == GenerationOptions()
    assert request.model is None


def test_request_rejects_an_empty_message_list():
    with pytest.raises(ValueError):
        LLMRequest(messages=[])


def test_request_rejects_an_unknown_role():
    with pytest.raises(ValueError):
        LLMRequest(messages=[{"role": "wizard", "content": "hi"}])


def test_provider_errors_share_a_base_class_and_carry_context():
    error = ProviderResponseError("bad payload", provider="minimal", model="minimal-1")

    assert isinstance(error, ProviderError)
    assert isinstance(error, Exception)
    assert error.message == "bad payload"
    assert error.provider == "minimal"
    assert error.model == "minimal-1"


@pytest.mark.asyncio
async def test_provider_error_propagates_to_the_caller():
    original = ProviderTimeoutError("upstream timed out", provider="minimal")

    with pytest.raises(ProviderTimeoutError) as excinfo:
        await ExplodingProvider(original).generate(user_request())

    assert excinfo.value is original
    assert str(excinfo.value) == "upstream timed out"


@pytest.mark.asyncio
async def test_generation_needs_no_external_llm_service(monkeypatch):
    """Generation must work with no credentials and no reachable LLM service.

    Name resolution is stubbed out because every real HTTP LLM client has to
    resolve a hostname before it can connect, so a provider that avoided this
    hook never needed a live service.
    """
    for variable in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_HOST", "LLM_PROVIDER"):
        monkeypatch.delenv(variable, raising=False)

    def no_name_resolution(*args: object, **kwargs: object) -> None:
        raise AssertionError("the provider must not resolve a hostname")

    monkeypatch.setattr(socket, "getaddrinfo", no_name_resolution)

    response = await MockLLMProvider().generate(user_request())

    assert response.text == "echo:hello"
