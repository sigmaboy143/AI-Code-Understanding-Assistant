"""Regression tests for evidence-grounded dependency results."""

from __future__ import annotations

import pytest

from app.orchestrator import OrchestratorService
from app.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.retrieval.base import RetrievedChunk
from app.schemas import AnalysisType, CodeUnderstandingRequest, DependencyKind


class _MockProvider(LLMProvider):
    """Deterministic provider that can make an unsupported textual claim."""

    def __init__(self, response_text: str = 'Analysis result.') -> None:
        self.response_text = response_text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.response_text)


def _request(source_code: str, **overrides: str) -> CodeUnderstandingRequest:
    values = {
        'source_code': source_code,
        'language': 'python',
        'analyses': [AnalysisType.DEPENDENCIES],
    }
    values.update(overrides)
    return CodeUnderstandingRequest(**values)


async def _analyse(source_code: str, **overrides: str):
    service = OrchestratorService(provider=_MockProvider())
    return await service.analyse(_request(source_code, **overrides))


@pytest.mark.asyncio
async def test_function_without_imports_has_no_dependencies():
    result = await _analyse('def add(a, b):\n    return a + b\n')

    assert result.dependencies is not None
    assert result.dependencies.dependencies == []


@pytest.mark.asyncio
async def test_explicit_import_is_returned_as_supported_dependency():
    result = await _analyse('import math\n\ndef add(a, b):\n    return a + b\n')

    assert [(item.name, item.kind) for item in result.dependencies.dependencies] == [
        ('math', DependencyKind.STANDARD_LIBRARY),
    ]


@pytest.mark.asyncio
async def test_multiple_explicit_imports_return_only_imported_dependencies():
    result = await _analyse('import math\nfrom pathlib import Path\n')

    assert [item.name for item in result.dependencies.dependencies] == ['math', 'pathlib']


@pytest.mark.asyncio
async def test_no_dependency_evidence_returns_an_empty_dependency_list():
    result = await _analyse('value = 42\n')

    assert result.dependencies is not None
    assert result.dependencies.dependencies == []


@pytest.mark.asyncio
async def test_retrieved_import_evidence_is_preserved():
    service = OrchestratorService(provider=_MockProvider())
    chunk = RetrievedChunk(
        chunk_id='dependency-evidence',
        file_path='src/related.py',
        content='import json\n',
        relevance_score=1.0,
    )

    result = await service.analyse(_request('value = 42\n'), [chunk])

    assert [item.name for item in result.dependencies.dependencies] == ['json']


@pytest.mark.asyncio
async def test_unsupported_llm_dependency_claim_is_not_structured_as_supported():
    service = OrchestratorService(provider=_MockProvider('This code depends on math.'))

    result = await service.analyse(_request('def add(a, b):\n    return a + b\n'))

    assert result.dependencies is not None
    assert result.dependencies.dependencies == []


@pytest.mark.asyncio
async def test_existing_explicit_import_behavior_is_stable_with_llm_claims():
    service = OrchestratorService(provider=_MockProvider('This code depends on requests.'))

    result = await service.analyse(_request('import requests\n'))

    assert [item.name for item in result.dependencies.dependencies] == ['requests']
    assert result.dependencies.dependencies[0].kind is DependencyKind.EXTERNAL
