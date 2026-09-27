"""Contract-level integration tests: dependency grounding through the HTTP API.

Category
--------
**Integration.** Real FastAPI application via ``TestClient``.

Scope
-----
Dependency grounding as observed by a *client*, which is the only perspective
that matters for the contract.  A caller must be able to rely on:

- every returned dependency is literally present in an ``import`` statement in
  the submitted source or the supplied context
- nothing is invented from free-text model output
- unparseable supplementary evidence yields an empty list, not a guess
- non-Python sources yield an empty list, not a guess
- the result is stable across different model answers

Why it exists
-------------
``tests/test_dependency_grounding.py`` already covers the orchestrator-level
behaviour.  What it does not cover is the same guarantee surviving JSON
serialisation over HTTP, and the ``extra="forbid"`` schema on ``Dependency``
that would reject a malformed entry at the boundary.  A grounding bug that only
manifests after serialisation would be invisible to the unit-level suite.
"""

from __future__ import annotations

import ast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures import (
    DEPENDENCIES_SOURCE,
    EXPLANATION_TEXT,
    EXPECTED_GROUNDED_DEPENDENCIES,
    EXPECTED_UNGROUNDED_DEPENDENCIES,
    MALFORMED_CHUNK_CONTENT,
    SIMPLE_SOURCE,
    EXTERNAL_CHUNK,
    INTERNAL_CHUNK,
    dependencies_input,
    static_provider,
)

client = TestClient(app)

#: Dependencies the HTTP layer is allowed to emit for ``DEPENDENCIES_SOURCE``.
EXPECTED_NAMES = [name for name, _kind in EXPECTED_GROUNDED_DEPENDENCIES]


def _post(payload: dict, provider_text: str = EXPLANATION_TEXT) -> dict:
    """POST *payload* with fixed provider output; return the JSON body."""
    with patch("app.main._build_provider", return_value=static_provider(provider_text)):
        response = client.post("/api/v1/code-understanding", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _dependency_names(body: dict) -> list[str]:
    return [item["name"] for item in body["dependencies"]["dependencies"]]


def _assert_every_name_is_imported(names: list[str], *sources: str) -> None:
    """Every name in *names* must appear in a real import in *sources*.

    Parses each source with ``ast`` and compares against the set of top-level
    imported modules.  This is the check that would catch a fabricated entry.
    """
    imported: set[str] = set()
    for source in sources:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])

    for name in names:
        assert name in imported, f"'{name}' is not imported by any supplied source"


# ---------------------------------------------------------------------------
# Grounded output
# ---------------------------------------------------------------------------


def test_explicit_imports_are_returned():
    body = _post(dependencies_input().model_dump(mode="json", exclude_none=True))

    assert _dependency_names(body) == EXPECTED_NAMES


def test_every_returned_dependency_is_actually_imported():
    body = _post(dependencies_input().model_dump(mode="json", exclude_none=True))

    _assert_every_name_is_imported(_dependency_names(body), DEPENDENCIES_SOURCE)


def test_dependency_kinds_are_classified_correctly():
    body = _post(dependencies_input().model_dump(mode="json", exclude_none=True))

    kinds = {item["name"]: item["kind"] for item in body["dependencies"]["dependencies"]}
    assert kinds == {"math": "standard_library", "pathlib": "standard_library"}


def test_dependency_entries_carry_every_contracted_key():
    body = _post(dependencies_input().model_dump(mode="json", exclude_none=True))

    for item in body["dependencies"]["dependencies"]:
        assert set(item.keys()) == {"name", "kind", "version", "description"}


# ---------------------------------------------------------------------------
# Nothing is invented
# ---------------------------------------------------------------------------


def test_source_without_imports_yields_an_empty_list():
    payload = dependencies_input(source_code=SIMPLE_SOURCE).model_dump(
        mode="json", exclude_none=True
    )

    body = _post(payload)

    assert _dependency_names(body) == []


def test_free_text_dependency_claim_does_not_become_a_structured_dependency():
    """The model says `requests`; the source never imports it."""
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        provider_text="This module depends on the requests library.",
    )

    names = _dependency_names(body)
    assert "requests" not in names
    _assert_every_name_is_imported(names, DEPENDENCIES_SOURCE)


@pytest.mark.parametrize("hallucinated", EXPECTED_UNGROUNDED_DEPENDENCIES)
def test_no_unimported_library_is_ever_returned(hallucinated):
    body = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        provider_text=f"This code uses {hallucinated}.",
    )

    assert hallucinated not in _dependency_names(body)


def test_grounding_is_independent_of_the_model_answer():
    """Two contradictory model answers must not change the structured output."""
    first = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        provider_text="Only math.",
    )
    second = _post(
        dependencies_input().model_dump(mode="json", exclude_none=True),
        provider_text="Uses math, pathlib, requests, numpy and torch.",
    )

    assert _dependency_names(first) == _dependency_names(second)


def test_unparseable_evidence_is_ignored_rather_than_guessed():
    """Broken supplementary context must not yield speculative dependencies."""
    payload = dependencies_input(
        source_code=SIMPLE_SOURCE,
        context=MALFORMED_CHUNK_CONTENT,
    ).model_dump(mode="json")

    body = _post(payload)

    assert _dependency_names(body) == []


def test_non_python_source_yields_no_dependencies():
    """The extractor is Python-only; a Go snippet must produce an empty list."""
    payload = dependencies_input(
        source_code='package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("x") }\n',
        language="go",
    ).model_dump(mode="json")

    body = _post(payload)

    assert body["dependencies"] is not None
    assert body["dependencies"]["dependencies"] == []


def test_relative_import_is_classified_as_internal():
    payload = dependencies_input(
        source_code="from . import helpers\n",
    ).model_dump(mode="json", exclude_none=True)

    body = _post(payload)

    kinds = {item["name"]: item["kind"] for item in body["dependencies"]["dependencies"]}
    assert kinds["helpers"] == "internal"


# ---------------------------------------------------------------------------
# Context evidence
# ---------------------------------------------------------------------------


def test_import_supplied_as_python_context_is_grounded():
    """Supplementary context that *is* valid Python contributes dependencies."""
    payload = dependencies_input(
        source_code=SIMPLE_SOURCE,
        context="import json\n",
    ).model_dump(mode="json")

    body = _post(payload)

    assert "json" in _dependency_names(body)


def test_import_mentioned_in_prose_is_not_scraped_as_a_dependency():
    """Grounding is AST-based, not regex-based.

    English prose that happens to contain the words ``import json`` is not
    evidence of a dependency and must not become one.  This is the difference
    between grounding and guessing, and it is the property most likely to be
    broken by a well-meaning optimisation later.
    """
    payload = dependencies_input(
        source_code=SIMPLE_SOURCE,
        context="A sibling module does `import json` in its helper.",
    ).model_dump(mode="json")

    body = _post(payload)

    assert _dependency_names(body) == []


def test_dependency_from_evidence_chunk_is_grounded():
    """A retrieved chunk carrying an import contributes a grounded dependency.

    Over HTTP the chunk reaches the engine as ``context`` (the public request
    schema has no separate chunk field), so this mirrors the chunk body into
    ``context`` and asserts the same grounding rule holds.
    """
    payload = dependencies_input(source_code=SIMPLE_SOURCE).model_dump(
        mode="json", exclude_none=True
    )
    payload["context"] = EXTERNAL_CHUNK.content

    body = _post(payload)

    assert "json" in _dependency_names(body)


def test_chunk_without_imports_contributes_nothing():
    payload = dependencies_input(source_code=SIMPLE_SOURCE).model_dump(
        mode="json", exclude_none=True
    )
    payload["context"] = INTERNAL_CHUNK.content

    body = _post(payload)

    assert _dependency_names(body) == []


# ---------------------------------------------------------------------------
# Requesting dependencies is what makes the field appear
# ---------------------------------------------------------------------------


def test_dependencies_field_is_null_when_dependencies_not_requested():
    from tests.fixtures import explanation_input

    body = _post(explanation_input().model_dump(mode="json"))

    assert body["dependencies"] is None


def test_dependencies_field_is_null_even_when_imports_exist():
    """The field is opt-in: an explanation request must not leak into it."""
    from tests.fixtures import explanation_input

    body = _post(
        explanation_input(source_code=DEPENDENCIES_SOURCE).model_dump(
            mode="json", exclude_none=True
        )
    )

    assert body["dependencies"] is None
