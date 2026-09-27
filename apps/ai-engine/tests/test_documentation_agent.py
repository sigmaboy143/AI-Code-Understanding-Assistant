"""Tests for the Documentation Agent (Task 15A).

Coverage
--------
- Documented answer from supplied README
- Documented answer from api_docs, architecture_notes, config_docs
- Relevant documentation section selection
- Question answered from correct source
- Undocumented question → UNKNOWN
- No invented documentation
- Empty context → UNKNOWN
- Evidence items reference supplied documentation
- Confidence behaviour (CONFIRMED vs UNKNOWN)
"""

from __future__ import annotations

from app.agents.documentation import (
    DocumentationAgent,
    DocumentationContext,
    DocumentationResult,
)
from app.evidence.models import ConfidenceLevel, EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent() -> DocumentationAgent:
    return DocumentationAgent()


def _ctx_with_readme(question: str | None = None) -> DocumentationContext:
    return DocumentationContext(
        readme=(
            "# MyProject\n"
            "MyProject is a REST API for code analysis.\n"
            "## Installation\n"
            "Run `pip install -r requirements.txt`.\n"
        ),
        question=question,
    )


# ---------------------------------------------------------------------------
# 1. Import test
# ---------------------------------------------------------------------------


def test_documentation_agent_can_be_imported():
    assert DocumentationAgent is not None


def test_documentation_context_can_be_imported():
    assert DocumentationContext is not None


def test_documentation_result_can_be_imported():
    assert DocumentationResult is not None


# ---------------------------------------------------------------------------
# 2. Documented answer from supplied context
# ---------------------------------------------------------------------------


def test_analyse_returns_documentation_result():
    result = _agent().analyse(_ctx_with_readme())
    assert isinstance(result, DocumentationResult)


def test_readme_answered_question():
    ctx = _ctx_with_readme(question="How do I install MyProject?")
    result = _agent().analyse(ctx)
    # Should find the readme as the relevant source
    assert "UNKNOWN" not in result.answer or "readme" in result.answer.lower()


def test_documented_answer_from_readme():
    ctx = DocumentationContext(
        readme="The project uses FastAPI as the web framework.",
        question="What web framework is used?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED
    assert "readme" in result.answer.lower() or "fastapi" in result.answer.lower()


def test_documented_answer_from_api_docs():
    ctx = DocumentationContext(
        api_docs="POST /analyse — Analyse source code.",
        question="Where is the analyse endpoint?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED
    assert "api_docs" in result.answer.lower() or "analyse" in result.answer.lower()


def test_documented_answer_from_architecture_notes():
    ctx = DocumentationContext(
        architecture_notes="The system uses a layered architecture with an API layer and a DB layer.",
        question="What architecture is used?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_documented_answer_from_config_docs():
    ctx = DocumentationContext(
        config_docs="Set PROVIDER=ollama in .env to configure the LLM provider.",
        question="How is the provider configured?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED
    assert "config" in result.answer.lower() or "provider" in result.answer.lower()


def test_documented_answer_from_docstring():
    ctx = DocumentationContext(
        docstrings={"MyClass": "MyClass handles user authentication."},
        question="What does MyClass do?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_documented_answer_from_markdown_file():
    ctx = DocumentationContext(
        markdown_files={"CONTRIBUTING.md": "To contribute, fork the repo and open a pull request."},
        question="How should I contribute to the repo?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# 3. Relevant documentation section selection
# ---------------------------------------------------------------------------


def test_relevant_sections_populated():
    ctx = _ctx_with_readme(question="What is MyProject?")
    result = _agent().analyse(ctx)
    assert len(result.relevant_sections) > 0


def test_relevant_section_source_label():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    sources = [s.source for s in result.relevant_sections]
    assert "readme" in sources


def test_all_supplied_sources_have_sections():
    ctx = DocumentationContext(
        readme="A README.",
        api_docs="API docs.",
        architecture_notes="Arch notes.",
    )
    result = _agent().analyse(ctx)
    sources = {s.source for s in result.relevant_sections}
    assert "readme" in sources
    assert "api_docs" in sources
    assert "architecture_notes" in sources


def test_documented_facts_list_supplied_sources():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    assert len(result.documented_facts) > 0


# ---------------------------------------------------------------------------
# 4. Undocumented question → UNKNOWN
# ---------------------------------------------------------------------------


def test_undocumented_question_returns_unknown():
    ctx = DocumentationContext(
        readme="This is a REST API for code analysis.",
        question="What is the company revenue?",
    )
    result = _agent().analyse(ctx)
    assert "UNKNOWN" in result.answer


def test_undocumented_question_confidence_unknown():
    ctx = DocumentationContext(
        readme="This is a REST API for code analysis.",
        question="What is the company revenue?",
    )
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_returns_unknown():
    ctx = DocumentationContext()
    result = _agent().analyse(ctx)
    assert "UNKNOWN" in result.answer


def test_empty_context_confidence_unknown():
    ctx = DocumentationContext()
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_limitations_present():
    ctx = DocumentationContext()
    result = _agent().analyse(ctx)
    assert len(result.limitations) > 0


# ---------------------------------------------------------------------------
# 5. No invented documentation
# ---------------------------------------------------------------------------


def test_no_invented_documentation_facts():
    """The agent must not add facts not present in the supplied documentation."""
    ctx = DocumentationContext(readme="Simple readme.")
    result = _agent().analyse(ctx)
    # documented_facts should only reference supplied sources
    for fact in result.documented_facts:
        # Each documented fact should mention a source name
        assert any(
            source in fact.lower()
            for source in ("readme", "api_docs", "architecture", "config", "markdown", "docstring")
        )


def test_no_fabricated_answer_from_empty_docs():
    ctx = DocumentationContext(readme="Simple readme.", question="What is XYZZY?")
    result = _agent().analyse(ctx)
    # Should say UNKNOWN, not invent an answer about XYZZY
    assert "UNKNOWN" in result.answer or result.confidence.level == ConfidenceLevel.UNKNOWN


# ---------------------------------------------------------------------------
# 6. Evidence items
# ---------------------------------------------------------------------------


def test_evidence_items_reference_documentation_source_type():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.DOCUMENTATION in source_types


def test_no_git_evidence_fabricated():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


def test_confirmed_confidence_with_readme():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_confidence_notes_present():
    ctx = _ctx_with_readme()
    result = _agent().analyse(ctx)
    assert result.confidence.notes is not None


# ---------------------------------------------------------------------------
# 7. No-question path (summary mode)
# ---------------------------------------------------------------------------


def test_no_question_returns_source_list():
    ctx = DocumentationContext(readme="README content.", api_docs="API docs content.")
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED
    # The answer should describe available sources
    assert result.answer


def test_no_question_limitation_noted():
    ctx = DocumentationContext(readme="README content.")
    result = _agent().analyse(ctx)
    assert any("no question" in lim.lower() for lim in result.limitations)


# ---------------------------------------------------------------------------
# 8. Excerpt truncation
# ---------------------------------------------------------------------------


def test_excerpt_truncated_for_long_content():
    long_doc = "x" * 1000
    ctx = DocumentationContext(readme=long_doc)
    result = _agent().analyse(ctx)
    section = next(s for s in result.relevant_sections if s.source == "readme")
    # excerpt should be <= 303 chars (300 + "...")
    assert len(section.excerpt) <= 303
