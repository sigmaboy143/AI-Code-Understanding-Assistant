"""Deterministic, evidence-grounded dependency extraction.

This module intentionally does not read dependency names from LLM output.
Dependencies in the public response are produced only from explicit Python
``import`` / ``from ... import`` statements present in supplied source or
retrieved code evidence.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable

from app.schemas.code_understanding import Dependency, DependencyAnalysis, DependencyKind


def build_dependency_analysis(
    source_code: str,
    evidence_texts: Iterable[str] = (),
) -> DependencyAnalysis:
    """Return dependencies directly established by supplied Python code.

    Invalid or non-code supplementary evidence is ignored rather than guessed
    from.  This deliberately favours an empty dependency list over an
    unsupported claim.
    """
    dependencies = [
        Dependency(name=name, kind=kind)
        for name, kind in _extract_dependencies_with_kinds(
            source_code, tuple(evidence_texts)
        )
    ]
    return DependencyAnalysis(dependencies=dependencies)


def _extract_dependencies_with_kinds(
    source_code: str,
    evidence_texts: Iterable[str],
) -> list[tuple[str, DependencyKind]]:
    """Extract unique dependencies in first-seen order with their source kind."""
    dependencies: list[tuple[str, DependencyKind]] = []
    seen: set[str] = set()
    for text in (source_code, *evidence_texts):
        for name, kind in _extract_python_imports(text):
            if name not in seen:
                seen.add(name)
                dependencies.append((name, kind))
    return dependencies


def _extract_python_imports(text: str) -> list[tuple[str, DependencyKind]]:
    """Extract only syntactically valid, explicit Python imports from *text*."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, TypeError):
        return []

    dependencies: list[tuple[str, DependencyKind]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.append(_dependency_from_module(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # A relative import is explicitly internal, even when its
                # module is omitted (for example ``from . import helpers``).
                name = node.module.split(".")[0] if node.module else node.names[0].name
                dependencies.append((name, DependencyKind.INTERNAL))
            elif node.module:
                dependencies.append(_dependency_from_module(node.module))
    return dependencies


def _dependency_from_module(module: str) -> tuple[str, DependencyKind]:
    """Normalise a module path to its top-level directly imported package."""
    name = module.split(".")[0]
    kind = (
        DependencyKind.STANDARD_LIBRARY
        if name in sys.stdlib_module_names
        else DependencyKind.EXTERNAL
    )
    return name, kind
