"""Tests for the bundled offline provider, which stands in for a real one."""

import pytest

from app.providers import (
    FinishReason,
    GenerationOptions,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
)
from app.providers.base import ProviderError, ProviderResponseError
from app.providers.mock import MockLLMProvider


def user_request(text: str = "hello") -> LLMRequest:
    return LLMRequest(messages=[Message(role=MessageRole.USER, content=text)])


def test_provider_reports_its_own_identification():
    provider = MockLLMProvider()

    assert provider.provider_name == "mock"
    assert provider.model == "mock-echo-1"


def test_provider_name_and_model_are_configurable():
    provider = MockLLMProvider(provider_name="stub", model="stub-1")

    assert provider.provider_name == "stub"
    assert provider.model == "stub-1"


def test_empty_canned_responses_are_rejected():
    with pytest.raises(ValueError):
        MockLLMProvider(responses=[])


@pytest.mark.asyncio
async def test_generate_echoes_the_last_user_message_by_default():
    response = await MockLLMProvider().generate(user_request("what is this?"))

    assert response.text == "echo:what is this?"


@pytest.mark.asyncio
async def test_generate_returns_the_expected_typed_structure():
    response = await MockLLMProvider().generate(user_request("hi there"))

    assert isinstance(response, LLMResponse)
    assert response.text == "echo:hi there"
    assert response.provider == "mock"
    assert response.model == "mock-echo-1"
    assert response.finish_reason is FinishReason.STOP
    assert response.usage == TokenUsage(
        prompt_tokens=2,
        completion_tokens=2,
        total_tokens=4,
    )
    assert response.raw is None


@pytest.mark.asyncio
async def test_generate_uses_the_conversation_history():
    request = LLMRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="be terse"),
            Message(role=MessageRole.USER, content="first"),
            Message(role=MessageRole.ASSISTANT, content="ok"),
            Message(role=MessageRole.USER, content="second"),
        ]
    )

    response = await MockLLMProvider().generate(request)

    assert response.text == "echo:second"
    assert response.usage is not None and response.usage.prompt_tokens == 5


@pytest.mark.asyncio
async def test_canned_responses_are_returned_in_order():
    provider = MockLLMProvider(responses=["first", "second"])

    assert (await provider.generate(user_request())).text == "first"
    assert (await provider.generate(user_request())).text == "second"
    # Exhausted list repeats the last entry instead of raising IndexError.
    assert (await provider.generate(user_request())).text == "second"
    assert provider.call_count == 3


@pytest.mark.asyncio
async def test_request_model_override_wins_over_provider_default():
    response = await MockLLMProvider().generate(
        LLMRequest(messages=user_request().messages, model="other-model")
    )

    assert response.model == "other-model"
    assert response.provider == "mock"


@pytest.mark.asyncio
async def test_generation_options_are_accepted_without_provider_specific_fields():
    request = LLMRequest(
        messages=user_request().messages,
        options=GenerationOptions(temperature=0.2, max_tokens=128, stop=("</s>",)),
    )

    response = await MockLLMProvider().generate(request)

    assert response.text == "echo:hello"


@pytest.mark.asyncio
async def test_failures_are_reported_as_provider_errors():
    request = LLMRequest(messages=[Message(role=MessageRole.SYSTEM, content="hi")])

    with pytest.raises(ProviderResponseError) as excinfo:
        await MockLLMProvider().generate(request)

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.provider == "mock"
    assert excinfo.value.model == "mock-echo-1"
