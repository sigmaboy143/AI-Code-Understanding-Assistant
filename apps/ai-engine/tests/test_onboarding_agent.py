"""Tests for the Repository Onboarding Agent (Task 16).

Coverage
--------
- Project overview from supplied context
- Entry-point extraction
- Important-file suggestions from supplied context
- Major component identification
- Development flow from supplied commands
- Documentation references
- Test references
- Suggested starting points
- Incomplete repository context → UNKNOWN
- No fabricated workflow, project purpose, or architecture
- Evidence and confidence behaviour
- Sections structure
"""

from __future__ import annotations

from app.agents.onboarding import (
    OnboardingAgent,
    OnboardingContext,
    OnboardingResult,
)
from app.evidence.models import ConfidenceLevel, EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent() -> OnboardingAgent:
    return OnboardingAgent()


def _full_context() -> OnboardingContext:
    return OnboardingContext(
        project_name="CodeAnalyser",
        project_description="A tool for automated code analysis and review.",
        language="Python",
        modules=["api", "db", "analysis"],
        files=["src/main.py", "src/config.py", "src/analysis.py"],
        entry_points=["src/main.py"],
        documentation=(
            "# CodeAnalyser\n"
            "CodeAnalyser is a REST API that analyses source code.\n"
            "## Getting Started\n"
            "Run `pip install -r requirements.txt`, then `python src/main.py`.\n"
        ),
        tests=["test_api.py", "test_analysis.py"],
        development_commands={
            "install": "pip install -r requirements.txt",
            "test": "pytest tests/",
            "lint": "ruff check .",
        },
        dependencies=["fastapi", "pydantic", "httpx"],
    )


# ---------------------------------------------------------------------------
# 1. Import test
# ---------------------------------------------------------------------------


def test_onboarding_agent_can_be_imported():
    assert OnboardingAgent is not None


def test_onboarding_context_can_be_imported():
    assert OnboardingContext is not None


def test_onboarding_result_can_be_imported():
    assert OnboardingResult is not None


# ---------------------------------------------------------------------------
# 2. Project overview from supplied context
# ---------------------------------------------------------------------------


def test_onboard_returns_onboarding_result():
    result = _agent().onboard(_full_context())
    assert isinstance(result, OnboardingResult)


def test_project_overview_contains_project_name():
    result = _agent().onboard(_full_context())
    assert "CodeAnalyser" in result.project_overview


def test_project_overview_contains_description():
    result = _agent().onboard(_full_context())
    assert "code analysis" in result.project_overview.lower()


def test_project_overview_contains_language():
    result = _agent().onboard(_full_context())
    assert "Python" in result.project_overview


def test_project_overview_without_description():
    ctx = OnboardingContext(project_name="MyProject")
    result = _agent().onboard(ctx)
    assert "MyProject" in result.project_overview


def test_project_overview_from_documentation_when_no_description():
    ctx = OnboardingContext(
        documentation="MyProject is a data processing pipeline."
    )
    result = _agent().onboard(ctx)
    assert "UNKNOWN" not in result.project_overview
    # Should use documentation as fallback
    assert "data processing" in result.project_overview.lower()


def test_empty_context_overview_is_unknown():
    ctx = OnboardingContext()
    result = _agent().onboard(ctx)
    assert "UNKNOWN" in result.project_overview


# ---------------------------------------------------------------------------
# 3. Entry-point extraction
# ---------------------------------------------------------------------------


def test_entry_points_extracted():
    result = _agent().onboard(_full_context())
    assert "src/main.py" in result.entry_points


def test_multiple_entry_points_extracted():
    ctx = OnboardingContext(entry_points=["main.py", "cli.py"])
    result = _agent().onboard(ctx)
    assert "main.py" in result.entry_points
    assert "cli.py" in result.entry_points


def test_no_entry_points_produces_limitation():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("entry" in lim.lower() for lim in result.limitations)
    assert found


def test_entry_points_section_in_sections():
    result = _agent().onboard(_full_context())
    titles = [s.title for s in result.sections]
    assert "Entry Points" in titles


def test_entry_point_section_confirmed():
    result = _agent().onboard(_full_context())
    ep_section = next(s for s in result.sections if s.title == "Entry Points")
    assert ep_section.confidence == ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# 4. Important-file suggestions from supplied context
# ---------------------------------------------------------------------------


def test_important_files_extracted():
    result = _agent().onboard(_full_context())
    assert "src/main.py" in result.important_files
    assert "src/config.py" in result.important_files


def test_no_files_produces_limitation():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("file" in lim.lower() for lim in result.limitations)
    assert found


def test_important_files_section_in_sections():
    result = _agent().onboard(_full_context())
    titles = [s.title for s in result.sections]
    assert "Important Files" in titles


# ---------------------------------------------------------------------------
# 5. Major components
# ---------------------------------------------------------------------------


def test_major_components_from_modules():
    result = _agent().onboard(_full_context())
    assert "api" in result.major_components
    assert "db" in result.major_components
    assert "analysis" in result.major_components


def test_no_modules_produces_limitation():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("module" in lim.lower() or "component" in lim.lower() for lim in result.limitations)
    assert found


# ---------------------------------------------------------------------------
# 6. Development flow from supplied commands
# ---------------------------------------------------------------------------


def test_development_flow_from_commands():
    result = _agent().onboard(_full_context())
    assert "install" in result.development_flow.lower()
    assert "pytest" in result.development_flow or "test" in result.development_flow.lower()


def test_development_flow_unknown_without_commands():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    assert "UNKNOWN" in result.development_flow


def test_development_flow_limitation_without_commands():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("command" in lim.lower() or "flow" in lim.lower() for lim in result.limitations)
    assert found


# ---------------------------------------------------------------------------
# 7. Documentation references
# ---------------------------------------------------------------------------


def test_documentation_referenced():
    result = _agent().onboard(_full_context())
    assert len(result.documentation_references) > 0


def test_no_documentation_produces_limitation():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("documentation" in lim.lower() for lim in result.limitations)
    assert found


def test_documentation_section_in_sections():
    result = _agent().onboard(_full_context())
    titles = [s.title for s in result.sections]
    assert "Documentation" in titles


def test_documentation_section_content_excerpt():
    result = _agent().onboard(_full_context())
    doc_section = next(s for s in result.sections if s.title == "Documentation")
    assert "CodeAnalyser" in doc_section.content or "code" in doc_section.content.lower()


# ---------------------------------------------------------------------------
# 8. Test references
# ---------------------------------------------------------------------------


def test_test_references_from_supplied_tests():
    result = _agent().onboard(_full_context())
    assert "test_api.py" in result.test_references
    assert "test_analysis.py" in result.test_references


def test_no_tests_produces_limitation():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    found = any("test" in lim.lower() for lim in result.limitations)
    assert found


# ---------------------------------------------------------------------------
# 9. Suggested starting points
# ---------------------------------------------------------------------------


def test_suggested_starting_points_populated():
    result = _agent().onboard(_full_context())
    assert len(result.suggested_starting_points) > 0


def test_starting_point_mentions_entry_point():
    result = _agent().onboard(_full_context())
    combined = " ".join(result.suggested_starting_points).lower()
    assert "main.py" in combined or "entry" in combined


def test_starting_point_mentions_documentation():
    result = _agent().onboard(_full_context())
    combined = " ".join(result.suggested_starting_points).lower()
    assert "documentation" in combined or "readme" in combined


def test_starting_point_mentions_tests():
    result = _agent().onboard(_full_context())
    combined = " ".join(result.suggested_starting_points).lower()
    assert "test" in combined


def test_no_starting_points_for_empty_context():
    ctx = OnboardingContext()
    result = _agent().onboard(ctx)
    # With empty context, sections content should be UNKNOWN
    sp_section = next(
        (s for s in result.sections if s.title == "Suggested Starting Points"), None
    )
    assert sp_section is not None
    assert "UNKNOWN" in sp_section.content or sp_section.confidence == ConfidenceLevel.UNKNOWN


# ---------------------------------------------------------------------------
# 10. Incomplete repository context → UNKNOWN
# ---------------------------------------------------------------------------


def test_empty_context_confidence_unknown():
    ctx = OnboardingContext()
    result = _agent().onboard(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_many_limitations():
    ctx = OnboardingContext()
    result = _agent().onboard(ctx)
    # Should have limitations for most missing fields
    assert len(result.limitations) >= 4


def test_partial_context_known_fields_confirmed():
    ctx = OnboardingContext(
        project_name="X",
        modules=["core"],
    )
    result = _agent().onboard(ctx)
    assert "core" in result.major_components


# ---------------------------------------------------------------------------
# 11. No fabricated workflow, project purpose, or architecture
# ---------------------------------------------------------------------------


def test_no_invented_project_name():
    ctx = OnboardingContext()
    result = _agent().onboard(ctx)
    # Must not invent a project name
    assert "CodeAnalyser" not in result.project_overview
    assert "MyProject" not in result.project_overview


def test_no_invented_modules():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    assert result.major_components == []


def test_no_invented_entry_points():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    assert result.entry_points == []


def test_no_invented_tests():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    assert result.test_references == []


def test_no_invented_development_commands():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    assert "UNKNOWN" in result.development_flow


# ---------------------------------------------------------------------------
# 12. Evidence and confidence behaviour
# ---------------------------------------------------------------------------


def test_confirmed_confidence_with_full_context():
    result = _agent().onboard(_full_context())
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_evidence_items_populated():
    result = _agent().onboard(_full_context())
    assert len(result.confidence.evidence) > 0


def test_evidence_references_supplied_files():
    result = _agent().onboard(_full_context())
    file_paths = [e.file_path for e in result.confidence.evidence if e.file_path]
    assert "src/main.py" in file_paths


def test_evidence_includes_documentation_source_type():
    result = _agent().onboard(_full_context())
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.DOCUMENTATION in source_types


def test_no_git_evidence_fabricated():
    result = _agent().onboard(_full_context())
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


def test_confidence_notes_present():
    result = _agent().onboard(_full_context())
    assert result.confidence.notes is not None


# ---------------------------------------------------------------------------
# 13. Sections structure
# ---------------------------------------------------------------------------


def test_all_sections_present():
    result = _agent().onboard(_full_context())
    titles = {s.title for s in result.sections}
    expected = {
        "Project Overview",
        "Entry Points",
        "Major Components",
        "Important Files",
        "Development Flow",
        "Documentation",
        "Tests",
        "Suggested Starting Points",
    }
    assert expected.issubset(titles)


def test_unknown_sections_marked_with_unknown_confidence():
    ctx = OnboardingContext(project_name="X")
    result = _agent().onboard(ctx)
    # Entry points section should be UNKNOWN
    ep_section = next(s for s in result.sections if s.title == "Entry Points")
    assert ep_section.confidence == ConfidenceLevel.UNKNOWN


def test_known_sections_marked_confirmed():
    ctx = OnboardingContext(modules=["core"])
    result = _agent().onboard(ctx)
    comp_section = next(s for s in result.sections if s.title == "Major Components")
    assert comp_section.confidence == ConfidenceLevel.CONFIRMED


# ---------------------------------------------------------------------------
# 14. Dependencies in project overview
# ---------------------------------------------------------------------------


def test_dependencies_in_project_overview():
    ctx = OnboardingContext(
        project_name="X",
        dependencies=["fastapi", "pydantic"],
    )
    result = _agent().onboard(ctx)
    assert "fastapi" in result.project_overview.lower()
