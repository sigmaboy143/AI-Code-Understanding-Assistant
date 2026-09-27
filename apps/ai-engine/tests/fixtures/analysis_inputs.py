"""Synthetic, safe source snippets and request builders.

Every snippet in this module is trivially small, hand-written, and unrelated to
any real repository.  Nothing here is confidential and nothing is read from
disk, so the fixtures are safe to commit and safe to run in CI.

The request builders return validated ``CodeUnderstandingRequest`` objects, so
an integration test can hand them straight to ``OrchestratorService`` or POST
them to ``/api/v1/code-understanding``.
"""

from __future__ import annotations

from app.schemas.code_understanding import (
    AnalysisType,
    CodeUnderstandingRequest,
    ProgrammingLanguage,
)

# ---------------------------------------------------------------------------
# Source snippets
# ---------------------------------------------------------------------------

SIMPLE_SOURCE = "def add(a, b):\n    return a + b\n"
"""The canonical two-line snippet.  No imports, therefore no grounded deps."""

SIMPLE_FILE_PATH = "src/math_ops.py"
"""Synthetic repository-relative path used for evidence attribution checks."""

DEPENDENCIES_SOURCE = (
    "import math\n"
    "from pathlib import Path\n"
    "\n"
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def area(radius):\n"
    "    return math.pi * radius ** 2\n"
    "\n"
    "def config_path():\n"
    "    return Path('app.json')\n"
)
"""Two standard-library imports and no external ones.  Grounded deps are
``math`` and ``pathlib``; any external library named here would be fabricated."""

IMPROVABLE_SOURCE = (
    "def divide(a, b):\n"
    "    return a / b\n"
)
"""Divides without a zero guard — the synthetic basis for improvement advice."""

ERROR_SOURCE = (
    "def first(items):\n"
    "    return items[0]\n"
)
"""Indexes without a bounds check — the synthetic basis for error explanation."""

ERROR_LOG = (
    "Traceback (most recent call last):\n"
    '  File "app.py", line 7, in <module>\n'
    "    first([])\n"
    "IndexError: list index out of range\n"
)
"""Synthetic stack trace.  Invented, not captured from a real run."""

ERROR_CONTEXT = "The caller passes an empty list.\n"
"""Synthetic supplementary context accompanying ``ERROR_SOURCE``."""

ALL_ANALYSES: list[AnalysisType] = list(AnalysisType)
"""All five analysis types, matching the request schema default order."""


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _request(
    source_code: str,
    analyses: list[AnalysisType],
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Build a validated request from a snippet and an analysis selection.

    ``overrides`` is applied last, so a caller can replace any field of the
    intent-specific default (for example ``language`` or ``file_path``).

    Each builder below therefore folds its own defaults into ``overrides``
    *before* calling this function, rather than passing them alongside it.
    Passing both would raise ``TypeError: got multiple values for keyword
    argument`` the moment a caller tried to override that field, which would
    silently make the documented override contract unusable.
    """
    values: dict[str, object] = {
        "source_code": source_code,
        "language": ProgrammingLanguage.PYTHON,
        "analyses": analyses,
    }
    values.update(overrides)
    return CodeUnderstandingRequest(**values)  # type: ignore[arg-type]


def explanation_input(
    source_code: str = SIMPLE_SOURCE,
    analyses: list[AnalysisType] | None = None,
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Request asking for an explanation of a trivial snippet.

    ``source_code`` and ``analyses`` default to the intent but may be replaced,
    so one builder serves both the "explanation only" and "every analysis"
    cases without duplicating the payload.
    """
    values: dict[str, object] = {"file_path": SIMPLE_FILE_PATH}
    values.update(overrides)
    return _request(
        source_code,
        [AnalysisType.EXPLANATION] if analyses is None else analyses,
        **values,
    )


def error_explanation_input(
    source_code: str = ERROR_SOURCE,
    analyses: list[AnalysisType] | None = None,
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Request asking for an error explanation, with a synthetic trace.

    The default ``context`` is the synthetic trace and its caller note; pass
    ``context=`` to replace it.
    """
    values: dict[str, object] = {
        "file_path": SIMPLE_FILE_PATH,
        "context": ERROR_CONTEXT + ERROR_LOG,
    }
    values.update(overrides)
    return _request(
        source_code,
        [AnalysisType.ERROR_EXPLANATION] if analyses is None else analyses,
        **values,
    )


def structure_input(
    source_code: str = SIMPLE_SOURCE,
    analyses: list[AnalysisType] | None = None,
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Request asking for a structural outline."""
    values: dict[str, object] = {"file_path": SIMPLE_FILE_PATH}
    values.update(overrides)
    return _request(
        source_code,
        [AnalysisType.STRUCTURE] if analyses is None else analyses,
        **values,
    )


def dependencies_input(
    source_code: str = DEPENDENCIES_SOURCE,
    analyses: list[AnalysisType] | None = None,
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Request asking for dependencies, over a snippet with two stdlib imports."""
    values: dict[str, object] = {"file_path": SIMPLE_FILE_PATH}
    values.update(overrides)
    return _request(
        source_code,
        [AnalysisType.DEPENDENCIES] if analyses is None else analyses,
        **values,
    )


def improvements_input(
    source_code: str = IMPROVABLE_SOURCE,
    analyses: list[AnalysisType] | None = None,
    **overrides: object,
) -> CodeUnderstandingRequest:
    """Request asking for improvement suggestions."""
    values: dict[str, object] = {"file_path": SIMPLE_FILE_PATH}
    values.update(overrides)
    return _request(
        source_code,
        [AnalysisType.IMPROVEMENTS] if analyses is None else analyses,
        **values,
    )
