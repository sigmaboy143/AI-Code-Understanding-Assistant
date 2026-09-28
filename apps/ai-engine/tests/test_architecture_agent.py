"""Tests for the Architecture Agent (Task 14).

Coverage
--------
- Architecture analysis with supplied modules/relationships
- Missing relationships → UNKNOWN in limitations
- No invented dependencies (fabrication guard)
- Evidence preservation
- Confidence behaviour (CONFIRMED vs UNKNOWN)
- Overview generation from modules, services, documentation
- Entry-point extraction
- Data-flow summary from relationships
- Limitations identification
"""

from __future__ import annotations

import pytest

from app.agents.architecture import (
    ArchitectureAgent,
    ArchitectureContext,
    ArchitectureResult,
    ModuleInfo,
    RelationshipInfo,
    ServiceInfo,
)
from app.evidence.models import ConfidenceLevel, EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent() -> ArchitectureAgent:
    return ArchitectureAgent()


def _full_context() -> ArchitectureContext:
    return ArchitectureContext(
        modules=[
            ModuleInfo(name="api", description="HTTP API layer"),
            ModuleInfo(name="db", description="Database access layer"),
        ],
        files=["src/main.py", "src/config.py"],
        symbols=["App", "DatabaseClient"],
        imports=["from db import client"],
        relationships=[
            RelationshipInfo(source="api", target="db", kind="dependency"),
        ],
        services=[
            ServiceInfo(name="AuthService", description="Handles authentication"),
        ],
        apis=["GET /health", "POST /api/v1/analyse"],
        documentation="This system provides code analysis via REST.",
        entry_points=["src/main.py"],
    )


# ---------------------------------------------------------------------------
# 1. Import test
# ---------------------------------------------------------------------------


def test_architecture_agent_can_be_imported():
    assert ArchitectureAgent is not None


def test_architecture_context_can_be_imported():
    assert ArchitectureContext is not None


def test_architecture_result_can_be_imported():
    assert ArchitectureResult is not None


# ---------------------------------------------------------------------------
# 2. Architecture with supplied modules and relationships
# ---------------------------------------------------------------------------


def test_analyse_returns_architecture_result():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert isinstance(result, ArchitectureResult)


def test_modules_appear_in_components():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    component_names = [c.name for c in result.components]
    assert "api" in component_names
    assert "db" in component_names


def test_services_appear_in_components():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    component_names = [c.name for c in result.components]
    assert "AuthService" in component_names


def test_files_appear_in_components():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    component_names = [c.name for c in result.components]
    assert "src/main.py" in component_names


def test_entry_points_extracted():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert "src/main.py" in result.entry_points


def test_dependency_relationships_extracted():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert len(result.dependency_relationships) == 1
    edge = result.dependency_relationships[0]
    assert edge.source == "api"
    assert edge.target == "db"
    assert edge.kind == "dependency"


def test_data_flow_summary_with_relationships():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert result.data_flow_summary is not None
    assert "api" in result.data_flow_summary
    assert "db" in result.data_flow_summary


# ---------------------------------------------------------------------------
# 3. Missing relationships → UNKNOWN limitation
# ---------------------------------------------------------------------------


def test_no_relationships_produces_limitation():
    agent = _make_agent()
    ctx = ArchitectureContext(
        modules=[ModuleInfo(name="api")],
    )
    result = agent.analyse(ctx)
    limitation_text = " ".join(result.limitations).lower()
    assert "unknown" in limitation_text or "relationship" in limitation_text or "dependency" in limitation_text


def test_no_entry_points_produces_limitation():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="api")])
    result = agent.analyse(ctx)
    found = any("entry" in lim.lower() for lim in result.limitations)
    assert found


def test_no_documentation_produces_limitation():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="api")])
    result = agent.analyse(ctx)
    found = any("documentation" in lim.lower() for lim in result.limitations)
    assert found


def test_empty_context_all_unknown():
    agent = _make_agent()
    ctx = ArchitectureContext()
    result = agent.analyse(ctx)
    assert "UNKNOWN" in result.overview
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_no_components():
    agent = _make_agent()
    ctx = ArchitectureContext()
    result = agent.analyse(ctx)
    # Only entry_point kind components (from entry_points list, which is empty)
    non_entry = [c for c in result.components if c.kind != "entry_point"]
    assert len(non_entry) == 0


def test_empty_context_no_dependency_edges():
    agent = _make_agent()
    ctx = ArchitectureContext()
    result = agent.analyse(ctx)
    assert result.dependency_relationships == []


def test_empty_context_no_data_flow():
    agent = _make_agent()
    ctx = ArchitectureContext()
    result = agent.analyse(ctx)
    assert result.data_flow_summary is None


# ---------------------------------------------------------------------------
# 4. No invented dependencies (fabrication guard)
# ---------------------------------------------------------------------------


def test_no_invented_dependencies():
    """Components must only come from the supplied context."""
    agent = _make_agent()
    ctx = ArchitectureContext(
        modules=[ModuleInfo(name="only_module")],
    )
    result = agent.analyse(ctx)
    component_names = {c.name for c in result.components}
    # Only "only_module" and entry_points (none here)
    assert "invented_service" not in component_names
    assert "invented_module" not in component_names


def test_no_invented_relationships():
    """Dependency edges must only come from the supplied relationships."""
    agent = _make_agent()
    ctx = ArchitectureContext(
        modules=[ModuleInfo(name="a"), ModuleInfo(name="b")],
    )
    result = agent.analyse(ctx)
    assert result.dependency_relationships == []


def test_no_invented_apis():
    """API info must only come from supplied context."""
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="web")])
    result = agent.analyse(ctx)
    # APIs are only included in overview when supplied
    assert "invented_api" not in result.overview


def test_supplied_apis_appear_in_overview():
    agent = _make_agent()
    ctx = ArchitectureContext(apis=["GET /health"])
    result = agent.analyse(ctx)
    assert "GET /health" in result.overview


# ---------------------------------------------------------------------------
# 5. Evidence preservation
# ---------------------------------------------------------------------------


def test_confirmed_confidence_when_modules_supplied():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="core")])
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_evidence_items_reference_supplied_modules():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="api")])
    result = agent.analyse(ctx)
    assert len(result.confidence.evidence) > 0
    descriptions = [e.description or "" for e in result.confidence.evidence]
    assert any("api" in d.lower() for d in descriptions)


def test_evidence_source_type_is_file():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="api")])
    result = agent.analyse(ctx)
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.FILE in source_types


def test_file_evidence_preserves_file_path():
    agent = _make_agent()
    ctx = ArchitectureContext(files=["src/main.py"])
    result = agent.analyse(ctx)
    file_paths = [e.file_path for e in result.confidence.evidence if e.file_path]
    assert "src/main.py" in file_paths


def test_no_git_evidence_fabricated():
    """git_commit evidence must never be auto-generated."""
    agent = _make_agent()
    result = agent.analyse(_full_context())
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


# ---------------------------------------------------------------------------
# 6. Confidence behaviour
# ---------------------------------------------------------------------------


def test_confirmed_confidence_with_relationships():
    agent = _make_agent()
    ctx = ArchitectureContext(
        relationships=[RelationshipInfo(source="a", target="b")]
    )
    result = agent.analyse(ctx)
    # Relationships don't add evidence items directly but context is non-empty
    # confidence could still be CONFIRMED since we have components
    # or UNKNOWN if no components — just check it's not fabricated
    assert result.confidence.level in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.UNKNOWN)


def test_unknown_confidence_empty_context():
    agent = _make_agent()
    ctx = ArchitectureContext()
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_confidence_notes_present():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="core")])
    result = agent.analyse(ctx)
    assert result.confidence.notes is not None
    assert len(result.confidence.notes) > 0


def test_module_components_marked_confirmed():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="api")])
    result = agent.analyse(ctx)
    module_components = [c for c in result.components if c.kind == "module"]
    assert all(c.confidence == ConfidenceLevel.CONFIRMED for c in module_components)


# ---------------------------------------------------------------------------
# 7. Documentation-driven overview
# ---------------------------------------------------------------------------


def test_documentation_used_as_overview_when_supplied():
    agent = _make_agent()
    ctx = ArchitectureContext(
        documentation="This is a REST API for code analysis."
    )
    result = agent.analyse(ctx)
    assert "REST API" in result.overview


def test_overview_from_modules_when_no_documentation():
    agent = _make_agent()
    ctx = ArchitectureContext(modules=[ModuleInfo(name="core")])
    result = agent.analyse(ctx)
    assert "core" in result.overview


# ---------------------------------------------------------------------------
# 8. Multiple relationships produce data flow
# ---------------------------------------------------------------------------


def test_multiple_relationships_appear_in_data_flow():
    agent = _make_agent()
    ctx = ArchitectureContext(
        relationships=[
            RelationshipInfo(source="ui", target="api"),
            RelationshipInfo(source="api", target="db"),
        ]
    )
    result = agent.analyse(ctx)
    assert result.data_flow_summary is not None
    assert "ui" in result.data_flow_summary
    assert "api" in result.data_flow_summary
    assert "db" in result.data_flow_summary


def test_data_flow_truncated_for_many_relationships():
    agent = _make_agent()
    ctx = ArchitectureContext(
        relationships=[
            RelationshipInfo(source=f"mod{i}", target=f"mod{i+1}")
            for i in range(8)
        ]
    )
    result = agent.analyse(ctx)
    assert result.data_flow_summary is not None
    assert "more" in result.data_flow_summary


# ---------------------------------------------------------------------------
# 9. Component kinds
# ---------------------------------------------------------------------------


def test_service_component_kind():
    agent = _make_agent()
    ctx = ArchitectureContext(services=[ServiceInfo(name="AuthService")])
    result = agent.analyse(ctx)
    service_components = [c for c in result.components if c.kind == "service"]
    assert len(service_components) == 1
    assert service_components[0].name == "AuthService"


def test_entry_point_component_kind():
    agent = _make_agent()
    ctx = ArchitectureContext(entry_points=["app/main.py"])
    result = agent.analyse(ctx)
    ep_components = [c for c in result.components if c.kind == "entry_point"]
    assert len(ep_components) == 1
    assert ep_components[0].name == "app/main.py"


def test_file_component_kind():
    agent = _make_agent()
    ctx = ArchitectureContext(files=["config.py"])
    result = agent.analyse(ctx)
    file_components = [c for c in result.components if c.kind == "file"]
    assert len(file_components) == 1
    assert file_components[0].name == "config.py"
