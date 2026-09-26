"""Test Analysis Agent (Task 15B).

Purpose
-------
Explain what tests exist and what behaviour they verify, using ONLY the
structured test context supplied by the caller.

The agent never:
- Builds or runs a test parser.
- Infers coverage that is not explicitly supplied.
- Invents test behaviour or coverage data.

Input context
-------------
``TestContext`` may contain:
- test_names         — list of test function/method names
- test_code          — {test_name: source_code} mapping
- test_descriptions  — {test_name: description} mapping
- target_symbol      — the symbol or file under test
- target_file        — the file under test
- coverage_info      — supplied coverage information (text or percentage)
- question           — an optional question about the test suite

Evidence and confidence
-----------------------
- CONFIRMED: claim directly supported by supplied test context
- INFERRED:  claim is a plausible conclusion from supplied context
- UNKNOWN:   required test context is absent

Limitations
-----------
- The agent does not parse source code.
- The agent does not run tests.
- The agent does not infer coverage beyond what is supplied.
- All facts are traceable to the supplied ``TestContext``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.evidence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    ResponseConfidence,
)


# ---------------------------------------------------------------------------
# Input context models
# ---------------------------------------------------------------------------


class SuiteContext(BaseModel):
    """Structured test context supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    test_names: list[str] = Field(
        default_factory=list,
        description="Names of test functions or test methods.",
    )
    test_code: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of {test_name: source_code}.",
    )
    test_descriptions: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of {test_name: human-readable description}.",
    )
    target_symbol: str | None = Field(
        default=None,
        description="The symbol (class, function) under test.",
    )
    target_file: str | None = Field(
        default=None,
        description="The file under test.",
    )
    coverage_info: str | None = Field(
        default=None,
        description="Supplied coverage information (text description or percentage).",
    )
    question: str | None = Field(
        default=None,
        description="Optional question about the test suite.",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class SuiteCaseSummary(BaseModel):
    """Summary of a single test case."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    has_code: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED


class SuiteAnalysisResult(BaseModel):
    """Structured output of the Test Agent.

    Fields
    ------
    overview:
        Summary of the test suite, or UNKNOWN when no context was supplied.
    tests:
        Per-test summaries derived from the supplied context.
    target_symbol:
        The symbol under test, if supplied.
    target_file:
        The file under test, if supplied.
    coverage_summary:
        Coverage information as supplied by the caller.  UNKNOWN when not supplied.
    related_tests:
        Test names that appear related to the same target (from supplied context).
    answer:
        Answer to the supplied question, or UNKNOWN.
    limitations:
        What the agent cannot determine from the supplied context.
    confidence:
        Evidence-backed confidence for this result.
    """

    model_config = ConfigDict(extra="forbid")

    overview: str
    tests: list[SuiteCaseSummary] = Field(default_factory=list)
    target_symbol: str | None = None
    target_file: str | None = None
    coverage_summary: str = Field(
        default="UNKNOWN: No coverage information was supplied."
    )
    related_tests: list[str] = Field(default_factory=list)
    answer: str | None = None
    limitations: list[str] = Field(default_factory=list)
    confidence: ResponseConfidence = Field(
        default_factory=ResponseConfidence.unknown,
    )




# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TestAgent:
    """Explains test suites from supplied structured test context.

    This agent is stateless.  Every call to ``analyse`` is independent.

    Usage::

        agent = TestAgent()
        result = agent.analyse(context)
    """

    def analyse(self, context: SuiteContext) -> SuiteAnalysisResult:
        """Produce a ``TestResult`` from the supplied context.

        Rules
        -----
        - Only use information present in *context*.
        - Return UNKNOWN for coverage unless it is explicitly supplied.
        - Never invent test behaviour or coverage data.
        - Build evidence items only from fields that are actually populated.

        Parameters
        ----------
        context:
            Structured test context supplied by the caller.

        Returns
        -------
        TestResult
            Deterministic result derived exclusively from the supplied context.
        """
        evidence: list[EvidenceItem] = []
        limitations: list[str] = []

        # ── No context at all ─────────────────────────────────────────────
        has_context = bool(
            context.test_names
            or context.test_code
            or context.test_descriptions
        )
        if not has_context:
            return SuiteAnalysisResult(
                overview="UNKNOWN: No test context was supplied.",
                coverage_summary="UNKNOWN: No coverage information was supplied.",
                limitations=[
                    "No test context was supplied. "
                    "Supply test_names, test_code, or test_descriptions."
                ],
                confidence=ResponseConfidence.unknown(
                    notes="No test context supplied."
                ),
            )

        # ── Build per-test summaries ──────────────────────────────────────
        tests = self._build_test_summaries(context, evidence)

        # ── Related tests ────────────────────────────────────────────────
        related = self._find_related_tests(context)

        # ── Coverage ─────────────────────────────────────────────────────
        if context.coverage_info:
            coverage_summary = context.coverage_info
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.TEST,
                    description="Supplied coverage information.",
                )
            )
        else:
            coverage_summary = "UNKNOWN: No coverage information was supplied."
            limitations.append(
                "No coverage information was supplied; coverage is UNKNOWN."
            )

        # ── Overview ─────────────────────────────────────────────────────
        overview = self._build_overview(context, tests)

        # ── Answer question ───────────────────────────────────────────────
        answer = self._answer_question(context)

        # ── Limitations ──────────────────────────────────────────────────
        if not context.target_symbol and not context.target_file:
            limitations.append(
                "No target symbol or file was supplied; "
                "test-to-symbol mapping is UNKNOWN."
            )

        # ── Confidence ───────────────────────────────────────────────────
        confidence = self._build_confidence(evidence)

        return SuiteAnalysisResult(
            overview=overview,
            tests=tests,
            target_symbol=context.target_symbol,
            target_file=context.target_file,
            coverage_summary=coverage_summary,
            related_tests=related,
            answer=answer,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_test_summaries(
        context: SuiteContext,
        evidence: list[EvidenceItem],
    ) -> list[SuiteCaseSummary]:
        """Build a summary for each known test."""
        summaries: list[SuiteCaseSummary] = []

        # Union of all known test names
        all_names: list[str] = list(
            dict.fromkeys(
                list(context.test_names)
                + list(context.test_code.keys())
                + list(context.test_descriptions.keys())
            )
        )

        for name in all_names:
            description = context.test_descriptions.get(name)
            has_code = name in context.test_code

            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.TEST,
                    description=f"Test '{name}' from supplied context.",
                )
            )

            summaries.append(
                SuiteCaseSummary(
                    name=name,
                    description=description,
                    has_code=has_code,
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )

        return summaries

    @staticmethod
    def _find_related_tests(context: SuiteContext) -> list[str]:
        """Identify tests related to the target symbol or file."""
        if not context.target_symbol and not context.target_file:
            return []

        target = (context.target_symbol or context.target_file or "").lower()
        related: list[str] = []

        all_names = list(
            dict.fromkeys(
                list(context.test_names)
                + list(context.test_code.keys())
                + list(context.test_descriptions.keys())
            )
        )

        for name in all_names:
            # Check name similarity
            if target and target.replace("/", "_").replace(".", "_") in name.lower():
                related.append(name)
                continue
            # Check test code for mentions of target
            code = context.test_code.get(name, "")
            if target and target in code.lower():
                related.append(name)

        return related

    @staticmethod
    def _build_overview(context: SuiteContext, tests: list[SuiteCaseSummary]) -> str:
        """Build a plain-language overview of the test suite."""
        count = len(tests)
        if count == 0:
            return "UNKNOWN: No tests found in the supplied context."

        parts: list[str] = [f"{count} test(s) found in the supplied context."]

        if context.target_symbol:
            parts.append(f"Target symbol: {context.target_symbol}.")
        if context.target_file:
            parts.append(f"Target file: {context.target_file}.")

        tests_with_desc = [t for t in tests if t.description]
        if tests_with_desc:
            parts.append(
                f"{len(tests_with_desc)} test(s) have descriptions."
            )

        tests_with_code = [t for t in tests if t.has_code]
        if tests_with_code:
            parts.append(
                f"{len(tests_with_code)} test(s) have supplied source code."
            )

        return " ".join(parts)

    @staticmethod
    def _answer_question(context: SuiteContext) -> str | None:
        """Answer the supplied question if one is provided."""
        if not context.question:
            return None

        question_lower = context.question.lower()

        # "what tests exist" / "list tests"
        if any(kw in question_lower for kw in ("what test", "list test", "which test")):
            all_names = list(
                dict.fromkeys(
                    list(context.test_names)
                    + list(context.test_code.keys())
                    + list(context.test_descriptions.keys())
                )
            )
            if all_names:
                return f"Tests in supplied context: {', '.join(all_names)}."
            return "UNKNOWN: No tests found in the supplied context."

        # "what does X test" / "what does X verify"
        if any(kw in question_lower for kw in ("what does", "what behavior", "what behaviour")):
            if context.test_descriptions:
                descriptions = "; ".join(
                    f"{k}: {v}" for k, v in context.test_descriptions.items()
                )
                return f"Supplied test descriptions: {descriptions}."
            return (
                "UNKNOWN: No test descriptions were supplied to answer "
                f"'{context.question}'."
            )

        # "coverage" questions
        if "coverage" in question_lower:
            if context.coverage_info:
                return f"Supplied coverage information: {context.coverage_info}."
            return "UNKNOWN: No coverage information was supplied."

        return (
            f"UNKNOWN: The supplied test context does not answer: '{context.question}'"
        )

    @staticmethod
    def _build_confidence(evidence: list[EvidenceItem]) -> ResponseConfidence:
        """Build confidence from accumulated evidence."""
        if evidence:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes="Test result derived directly from supplied test context.",
            )
        return ResponseConfidence.unknown(
            notes="Test context supplied but no evidence items could be built."
        )
