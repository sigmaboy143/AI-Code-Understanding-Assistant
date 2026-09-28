"""End-to-end user scenarios for the implemented developer-assistant capabilities.

Category
--------
**Integration / scenario.** Each test drives one complete user journey through
the *real* stack — real routing, real Pydantic validation, real context
assembly, real prompt construction, real provider call, real output validation,
real serialisation — and asserts the whole user-visible outcome.  Only the
outbound network hop is replaced, by a deterministic fixture.

How this differs from the rest of the suite
-------------------------------------------
The other integration modules are **contract** tests: they check one property at
a time, because a contract test that asserts five things reports one failure.
The evaluation module checks **trustworthiness** of an answer in isolation.

This module checks **journeys**: "a developer pastes a snippet and asks why it
is slow" is answered from what was supplied, attributes its evidence honestly,
and invents nothing.  That composition is what a user experiences and what no
single-property test can catch.

Scenario-to-capability mapping
------------------------------
The scenarios are pinned to what the engine actually implements.  This matters
because the seven agents in ``app/agents/`` are **not** wired into the HTTP
surface: ``main.py`` exposes exactly three paths and the analysis route goes
through ``OrchestratorService`` alone.  So each scenario below is expressed in
terms of the capability a user can actually invoke today:

======================  =========================================================
Scenario                How a user reaches it
======================  =========================================================
Code explanation        ``analyses=["explanation"]``
Why / reasoning         the ``question`` field, answered first
Relationships/context   the ``context`` field plus retrieved chunks
Impact analysis         ``analyses=["dependencies"]`` → ``dependencies.impacts``
Debugging               ``analyses=["error_explanation"]`` + error context
Onboarding              an onboarding question through the ordinary endpoint
======================  =========================================================

Agent-level behaviour is already covered by the seven ``test_*_agent.py``
modules.  This file deliberately does not re-test them; it covers the
orchestrated path and records the exposure boundary.

Honesty constraints observed here
---------------------------------
- No test asserts a structured field the orchestrator does not populate.
  ``OrchestratorService._parse_response`` sets only ``summary``, ``metadata``,
  ``confidence``, and ``dependencies``, so ``explanation``,
  ``error_explanation``, and ``structure`` are asserted ``None`` and
  ``improvements`` is asserted ``[]``.
- "Source code is reflected accurately" is verified as *the model was given the
  real snippet byte-for-byte* plus *structured output is derived from it*, not
  as a judgement about prose from a stub.
- No live LLM. Every provider is deterministic, so the suite runs in
  milliseconds and gives the same answer on every machine.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator import OrchestratorService
from app.retrieval.memory import InMemoryRetriever
from app.schemas.code_understanding import CodeUnderstandingRequest
from tests.fixtures import (
    ERROR_EXPLANATION_TEXT,
    EXPLANATION_TEXT,
    EXTERNAL_CHUNK,
    FABRICATED_REPOSITORY_FACTS,
    GIT_FACT_CLAIM_TEXT,
    INTERNAL_CHUNK,
    ONBOARDING_QUESTION_TEXT,
    UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT,
    chunk_list,
    dependencies_input,
    error_explanation_input,
    explanation_input,
    RecordingProvider,
)

client = TestClient(app)

#: The complete public surface.  Pinned so a new route cannot appear without a
#: deliberate decision about which scenario it serves.
PUBLIC_API_PATHS = frozenset({"/health", "/ready", "/api/v1/code-understanding"})


def _post(payload: dict, provider) -> dict:
    """POST *payload* with *provider* standing in for the LLM; return the body."""
    with patch("app.main._build_provider", return_value=provider):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def _analyse(request, provider, chunks=None):
    """Run *request* through the real orchestrator with a fixed provider."""
    return await OrchestratorService(provider=provider).analyse(request, chunks)


def _chunk_header(chunk) -> str:
    """The attribution header ``reasoning`` writes for *chunk* in the prompt.

    Derived from the chunk itself rather than hard-coded, so the assertion
    tracks the fixture instead of duplicating the format string.
    """
    header = f"[{chunk.source_type}] {chunk.file_path}"
    if chunk.symbol:
        header += f" — {chunk.symbol}"
    if chunk.line_start is not None:
        header += f" (lines {chunk.line_start}–{chunk.line_end})"
    return header


def _evidence_text(body: dict) -> str:
    """Flatten every evidence item into one searchable string."""
    return " ".join(
        f"{item.get('description') or ''} {item.get('file_path') or ''} "
        f"{item.get('chunk_id') or ''}"
        for item in body["confidence"]["evidence"]
    )


# ===========================================================================
# Scenario 1 — Code explanation
#
# "Paste a snippet, tell me what this does."
# ===========================================================================


def test_explanation_scenario_returns_a_usable_answer():
    """The whole journey produces a non-empty answer a developer can read."""
    body = _post(
        explanation_input().model_dump(mode="json"), RecordingProvider(EXPLANATION_TEXT)
    )

    assert body["summary"] == EXPLANATION_TEXT
    assert body["metadata"]["language"] == "python"
    assert body["metadata"]["analyses"] == ["explanation"]


def test_explanation_scenario_shows_the_engine_saw_the_real_snippet():
    """Accuracy is only possible if the exact snippet reaches the model.

    Asserting the prompt is the strongest available check with a stubbed
    provider: it proves the engine handed over the real bytes and the real
    language identifier, so any inaccuracy would be the model's, not the
    engine's prompt assembly.
    """
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=explanation_input().model_dump(mode="json"),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "def add(a, b):" in prompt
    assert "Language: python" in prompt
    assert "[EXPLANATION]" in prompt


def test_explanation_scenario_does_not_fabricate_repository_facts():
    """A confident-sounding story about commits must stay unstructural."""
    body = _post(
        explanation_input().model_dump(mode="json"),
        RecordingProvider(GIT_FACT_CLAIM_TEXT),
    )

    assert body["structure"] is None
    assert body["dependencies"] is None
    assert body["improvements"] == []
    for fact in FABRICATED_REPOSITORY_FACTS:
        assert fact not in _evidence_text(body)


def test_explanation_scenario_reports_confidence_honestly():
    """Free text is never CONFIRMED, and the reason must be explained."""
    body = _post(
        explanation_input().model_dump(mode="json"), RecordingProvider(EXPLANATION_TEXT)
    )

    assert body["confidence"]["level"] == "UNKNOWN"
    assert body["confidence"]["notes"].strip()
    assert body["confidence"]["evidence"]


# ===========================================================================
# Scenario 2 — Why / reasoning
#
# "Why is this function written this way?"
# ===========================================================================


def test_why_scenario_question_is_accepted_and_answered_first():
    """A question takes priority over the generic analysis instruction."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=explanation_input(
                question="Why does this return a float for two ints?"
            ).model_dump(mode="json"),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "Why does this return a float for two ints?" in prompt
    assert "answer this first" in prompt


def test_why_scenario_response_reflects_supplied_context():
    """Supplied context must arrive marked as ground truth, not as an aside."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=explanation_input(
                question="Why is this called from the CLI?",
                context="Called only by the CLI entry point in main.py.",
            ).model_dump(mode="json"),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "Called only by the CLI entry point in main.py." in prompt
    assert "treat as ground truth" in prompt


def test_why_scenario_instructs_the_model_to_declare_what_is_missing():
    """Absence of history is acknowledged by instruction, not by invention.

    The request schema carries no Git channel, so the engine cannot verify a
    "why".  The contract it can honour is telling the model to say so rather
    than fill the gap.  Both halves of that instruction are asserted.
    """
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=explanation_input(
                question="Why was the caching layer removed?"
            ).model_dump(mode="json"),
        )

    system_prompt = provider.requests[0].messages[0].content
    user_prompt = provider.requests[0].messages[-1].content
    assert "Do NOT invent Git history" in system_prompt
    assert "explicitly state what is missing" in user_prompt


def test_why_scenario_request_schema_has_no_history_channel():
    """There is no field through which Git history could silently arrive.

    Asserted on the schema rather than by posting an unknown key, because the
    generic "extra field is rejected" 422 case is already covered in
    ``test_request_contract.py``.  What matters here is the *absence* of a
    history channel, which is what makes the instruction above load-bearing.
    """
    fields = set(CodeUnderstandingRequest.model_fields)

    assert not fields & {"commit", "commits", "git_history", "history", "diff"}
    assert {"question", "context"} <= fields


def test_why_scenario_never_promotes_a_why_answer_into_structure():
    """Whatever the model asserts about motive stays in the summary."""
    body = _post(
        explanation_input(
            question="Why was the caching layer removed?"
        ).model_dump(mode="json"),
        RecordingProvider(GIT_FACT_CLAIM_TEXT),
    )

    assert body["structure"] is None
    assert body["improvements"] == []
    assert body["confidence"]["level"] == "UNKNOWN"


def test_why_scenario_confidence_stays_unknown_without_history_evidence():
    """Rich context is still not verification of a claim about intent."""
    body = _post(
        explanation_input(
            question="Why was the caching layer removed?",
            context="The team decided caching added no measurable benefit.",
        ).model_dump(mode="json"),
        RecordingProvider(EXPLANATION_TEXT),
    )

    assert body["confidence"]["level"] == "UNKNOWN"
    assert body["confidence"]["evidence"]


# ===========================================================================
# Scenario 3 — Relationships / context
#
# "Show me what this touches."
# ===========================================================================


def test_relationship_scenario_retrieval_finds_the_relevant_chunk():
    """Real retrieval selects the chunk whose content matches the question."""
    retriever = InMemoryRetriever(corpus=chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK))

    results = retriever.retrieve("clamp value between low and high", top_k=5)

    assert [chunk.chunk_id for chunk in results] == [INTERNAL_CHUNK.chunk_id]


async def test_relationship_scenario_retrieved_chunk_reaches_the_prompt_with_attribution():
    """The join that makes relationships possible at all.

    ``test_retrieval.py`` proves the reasoning layer renders chunks and
    ``test_context_builder.py`` proves it keeps them.  Neither proves that
    ``OrchestratorService.analyse`` actually passes the builder's output
    through to the provider — the step where a retrieved relationship silently
    disappearing would be invisible.
    """
    provider = RecordingProvider(EXPLANATION_TEXT)

    await _analyse(explanation_input(), provider, chunk_list(INTERNAL_CHUNK))

    prompt = provider.requests[0].messages[-1].content
    assert "Retrieved context" in prompt
    assert _chunk_header(INTERNAL_CHUNK) in prompt
    assert INTERNAL_CHUNK.content in prompt


async def test_relationship_scenario_orders_chunks_by_relevance():
    """The most relevant chunk must be presented first."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    await _analyse(
        explanation_input(), provider, chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK)
    )

    prompt = provider.requests[0].messages[-1].content
    assert INTERNAL_CHUNK.relevance_score > EXTERNAL_CHUNK.relevance_score
    assert prompt.index(_chunk_header(INTERNAL_CHUNK)) < prompt.index(
        _chunk_header(EXTERNAL_CHUNK)
    )


async def test_relationship_scenario_preserves_supplied_context_verbatim():
    """Caller-supplied related context is passed through untouched."""
    provider = RecordingProvider(EXPLANATION_TEXT)
    related = "A sibling module calls clamp() before persisting the value."

    await _analyse(explanation_input(context=related), provider)

    assert related in provider.requests[0].messages[-1].content


async def test_relationship_scenario_does_not_fabricate_relationships():
    """Naming systems the caller never supplied yields no structured output."""
    result = await _analyse(
        explanation_input(),
        RecordingProvider(UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT),
    )

    assert result.structure is None
    assert result.dependencies is None
    assert result.improvements == []

    rendered = " ".join(
        f"{item.description} {item.file_path}"
        for item in result.confidence.evidence
    )
    assert "billing" not in rendered
    assert "notification worker" not in rendered


async def test_relationship_scenario_evidence_references_only_retrieved_material():
    """Every evidence path is one the caller actually supplied."""
    supplied = {INTERNAL_CHUNK.file_path, EXTERNAL_CHUNK.file_path}

    result = await _analyse(
        explanation_input(),
        RecordingProvider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK, EXTERNAL_CHUNK),
    )

    referenced = {i.file_path for i in result.confidence.evidence if i.file_path}
    assert referenced
    assert referenced.issubset(supplied)


async def test_relationship_scenario_chunk_evidence_is_traceable():
    """A reader must be able to open exactly the chunk that was used."""
    result = await _analyse(
        explanation_input(),
        RecordingProvider(EXPLANATION_TEXT),
        chunk_list(INTERNAL_CHUNK),
    )

    item = next(i for i in result.confidence.evidence if i.chunk_id is not None)
    assert item.chunk_id == INTERNAL_CHUNK.chunk_id
    assert item.file_path == INTERNAL_CHUNK.file_path
    assert item.line_start == INTERNAL_CHUNK.line_start
    assert item.line_end == INTERNAL_CHUNK.line_end


# ===========================================================================
# Scenario 4 — Impact analysis
#
# "If I change this, what breaks?"
# ===========================================================================


def test_impact_scenario_reports_only_directly_supplied_dependencies():
    """Impact starts from imports that are actually present in the code."""
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        RecordingProvider(EXPLANATION_TEXT),
    )

    assert [item["name"] for item in body["dependencies"]["dependencies"]] == [
        "math",
        "pathlib",
    ]


def test_impact_scenario_never_invents_a_downstream_impact():
    """Claiming coupling must not manufacture an affected component.

    ``OrchestratorService`` has no caller-supplied component graph, so the only
    honest impact list is the empty one — even when the model confidently
    describes one.
    """
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        RecordingProvider(UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT),
    )

    assert body["dependencies"]["impacts"] == []


def test_impact_scenario_keeps_confidence_and_evidence_honest():
    """Impact is reported with UNKNOWN response confidence and real evidence."""
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        RecordingProvider(EXPLANATION_TEXT),
    )

    assert body["confidence"]["level"] == "UNKNOWN"
    assert body["confidence"]["evidence"]
    assert body["dependencies"]["dependencies"]


# ===========================================================================
# Scenario 5 — Debugging
#
# "Here is a stack trace. What went wrong?"
# ===========================================================================


def test_debug_scenario_accepts_error_context():
    """A synthetic trace reaches the model verbatim."""
    provider = RecordingProvider(ERROR_EXPLANATION_TEXT)
    request = error_explanation_input()

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=request.model_dump(mode="json"),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "IndexError: list index out of range" in prompt
    assert "items[0]" in prompt


def test_debug_scenario_instruction_requires_causes_and_fixes():
    """The error analysis is asked for causes and concrete fixes."""
    provider = RecordingProvider(ERROR_EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=error_explanation_input().model_dump(mode="json"),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "[ERROR_EXPLANATION]" in prompt
    assert "likely causes" in prompt.lower()
    assert "suggested fixes" in prompt.lower()


def test_debug_scenario_discussion_stays_inside_the_supplied_evidence():
    """The engine adds no file location the caller did not supply."""
    request = error_explanation_input()
    body = _post(request.model_dump(mode="json"), RecordingProvider(ERROR_EXPLANATION_TEXT))

    assert body["summary"] == ERROR_EXPLANATION_TEXT
    assert body["metadata"]["file_path"] == request.file_path
    for fact in FABRICATED_REPOSITORY_FACTS:
        assert fact not in _evidence_text(body)


def test_debug_scenario_suggested_fixes_invent_no_repository_facts():
    """Fixes described out loud must not become structured improvements."""
    body = _post(
        error_explanation_input().model_dump(mode="json"),
        RecordingProvider(GIT_FACT_CLAIM_TEXT),
    )

    assert body["improvements"] == []
    assert body["structure"] is None
    assert body["confidence"]["level"] == "UNKNOWN"
    for fact in FABRICATED_REPOSITORY_FACTS:
        assert fact not in _evidence_text(body)


# ===========================================================================
# Scenario 6 — Onboarding
#
# "I am new here. Where do I start?"
#
# There is no onboarding route.  ``OnboardingAgent`` exists in ``app/agents/``
# and is covered by ``test_onboarding_agent.py``, but it is not wired into
# ``main.py``.  These tests pin that boundary and verify the capability a user
# actually has today: an ordinary question, answered from what was supplied.
# ===========================================================================


def test_onboarding_scenario_is_not_exposed_as_its_own_api_capability():
    """The public surface is exactly three paths, and onboarding is not one.

    Recorded deliberately: if a future phase adds an onboarding route, this
    test fails and forces a decision about which scenario it serves, rather
    than the capability appearing silently and untested.
    """
    assert set(app.openapi()["paths"]) == set(PUBLIC_API_PATHS)


def test_onboarding_scenario_question_flows_through_the_ordinary_endpoint():
    """A new developer's question is accepted and answered normally."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        response = client.post(
            "/api/v1/code-understanding",
            json=explanation_input(question=ONBOARDING_QUESTION_TEXT).model_dump(
                mode="json"
            ),
        )

    assert response.status_code == 200
    assert response.json()["summary"] == EXPLANATION_TEXT
    assert ONBOARDING_QUESTION_TEXT in provider.requests[0].messages[-1].content


def test_onboarding_scenario_is_instructed_to_declare_missing_repository_information():
    """With no repository context supplied, the model is told to say so."""
    provider = RecordingProvider(EXPLANATION_TEXT)

    with patch("app.main._build_provider", return_value=provider):
        client.post(
            "/api/v1/code-understanding",
            json=explanation_input(question=ONBOARDING_QUESTION_TEXT).model_dump(
                mode="json"
            ),
        )

    prompt = provider.requests[0].messages[-1].content
    assert "explicitly state what is missing" in prompt


def test_onboarding_scenario_grounds_only_in_what_was_supplied():
    """No entry points, modules, or tests are invented for a new developer."""
    body = _post(
        explanation_input(question=ONBOARDING_QUESTION_TEXT).model_dump(mode="json"),
        RecordingProvider(UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT),
    )

    assert body["structure"] is None
    assert body["dependencies"] is None
    assert body["improvements"] == []
    assert body["confidence"]["level"] == "UNKNOWN"
    assert "billing" not in _evidence_text(body)


# ===========================================================================
# Cross-scenario invariants
# ===========================================================================


@pytest.mark.parametrize(
    "build",
    [
        explanation_input,
        error_explanation_input,
        dependencies_input,
    ],
    ids=["explanation", "error_explanation", "dependencies"],
)
def test_every_reachable_scenario_keeps_optional_fields_empty(build):
    """No journey may populate a structured field the orchestrator never sets.

    Encodes the current architecture as an executable fact.  When structured
    output is implemented, this test fails and each assertion gets a real
    expectation instead of silently passing against ``None``.
    """
    body = _post(build().model_dump(mode="json"), RecordingProvider(EXPLANATION_TEXT))

    assert body["explanation"] is None
    assert body["error_explanation"] is None
    assert body["structure"] is None

