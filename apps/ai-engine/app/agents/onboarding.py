"""Repository Onboarding Agent (Task 16).

Purpose
-------
Generate a structured onboarding guide for developers who are unfamiliar
with the repository, using ONLY the supplied repository-intelligence context.

The onboarding result covers:
1. Project overview
2. Important entry points
3. Major modules/components
4. Important files
5. Typical development flow
6. Relevant documentation
7. Relevant tests
8. Suggested starting points for a new developer

The agent never:
- Invents project purpose, architecture, or workflows.
- Fabricates file importance, deployment processes, or test coverage.
- Reads the file system directly.
- Calls any external service.

All aspects that cannot be determined from the supplied context are
explicitly marked UNKNOWN.

Input context
-------------
``OnboardingContext`` may contain:
- project_name           — project/repository name
- project_description    — short description of the project
- language               — primary programming language
- modules                — named modules/packages
- files                  — important file paths
- entry_points           — known entry points
- documentation          — documentation text (README, wiki, etc.)
- tests                  — test names or descriptions
- development_commands   — known development commands (build, test, lint)
- dependencies           — known external dependencies

Evidence and confidence
-----------------------
- CONFIRMED: fact directly supplied in context
- INFERRED:  plausible conclusion from supplied context
- UNKNOWN:   required information is absent

Limitations
-----------
- The agent does not scan the file system.
- The agent does not infer project purpose beyond what is supplied.
- All facts in the result are traceable to the supplied ``OnboardingContext``.
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


class OnboardingContext(BaseModel):
    """Structured repository-intelligence context for onboarding.

    All fields are optional.  Absent fields result in UNKNOWN aspects
    in the onboarding output.
    """

    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(
        default=None,
        description="Project or repository name.",
    )
    project_description: str | None = Field(
        default=None,
        description="Short description of the project's purpose.",
    )
    language: str | None = Field(
        default=None,
        description="Primary programming language.",
    )
    modules: list[str] = Field(
        default_factory=list,
        description="Named modules or packages in the repository.",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Important file paths discovered by upstream analysis.",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Known entry points (main files, CLI scripts, etc.).",
    )
    documentation: str | None = Field(
        default=None,
        description="Documentation text (README, wiki, etc.).",
    )
    tests: list[str] = Field(
        default_factory=list,
        description="Test names or test file paths.",
    )
    development_commands: dict[str, str] = Field(
        default_factory=dict,
        description="Known development commands, e.g. {'test': 'pytest', 'build': 'make'}.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Known external dependencies.",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class OnboardingSection(BaseModel):
    """A section of the onboarding guide with confidence annotation."""

    model_config = ConfigDict(extra="forbid")

    title: str
    content: str
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED


class OnboardingResult(BaseModel):
    """Structured onboarding guide produced by the Onboarding Agent.

    Fields
    ------
    project_overview:
        Short description of the project.  UNKNOWN when not supplied.
    entry_points:
        Known entry points from the supplied context.
    major_components:
        Major modules/components from the supplied context.
    important_files:
        Important files from the supplied context.
    development_flow:
        Typical development flow derived from supplied commands.
        UNKNOWN when commands are not supplied.
    documentation_references:
        Available documentation references.
    test_references:
        Available test references.
    suggested_starting_points:
        Suggested first steps for a new developer.
    sections:
        All onboarding sections in order, for structured rendering.
    limitations:
        Aspects the agent cannot determine from the supplied context.
    confidence:
        Evidence-backed confidence for the onboarding result.
    """

    model_config = ConfigDict(extra="forbid")

    project_overview: str
    entry_points: list[str] = Field(default_factory=list)
    major_components: list[str] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    development_flow: str
    documentation_references: list[str] = Field(default_factory=list)
    test_references: list[str] = Field(default_factory=list)
    suggested_starting_points: list[str] = Field(default_factory=list)
    sections: list[OnboardingSection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: ResponseConfidence = Field(
        default_factory=ResponseConfidence.unknown,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class OnboardingAgent:
    """Generates a developer onboarding guide from supplied repository context.

    This agent is stateless.  Every call to ``onboard`` is independent.

    Usage::

        agent = OnboardingAgent()
        result = agent.onboard(context)
    """

    def onboard(self, context: OnboardingContext) -> OnboardingResult:
        """Produce an ``OnboardingResult`` from the supplied context.

        Rules
        -----
        - Only use information present in *context*.
        - Mark every unknown aspect explicitly with UNKNOWN.
        - Never invent project purpose, architecture, workflows, or file importance.
        - Build evidence items only from fields that are actually populated.

        Parameters
        ----------
        context:
            Structured repository-intelligence context supplied by the caller.

        Returns
        -------
        OnboardingResult
            Deterministic result derived exclusively from the supplied context.
        """
        evidence: list[EvidenceItem] = []
        limitations: list[str] = []
        sections: list[OnboardingSection] = []

        # ── 1. Project overview ──────────────────────────────────────────
        project_overview, overview_confidence = self._build_overview(
            context, evidence
        )
        sections.append(
            OnboardingSection(
                title="Project Overview",
                content=project_overview,
                confidence=overview_confidence,
            )
        )

        # ── 2. Entry points ──────────────────────────────────────────────
        entry_points = list(context.entry_points)
        if entry_points:
            for ep in entry_points:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.FILE,
                        file_path=ep,
                        description=f"Entry point: {ep}",
                    )
                )
            sections.append(
                OnboardingSection(
                    title="Entry Points",
                    content=", ".join(entry_points),
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
        else:
            limitations.append("No entry points were supplied; entry-point identification is UNKNOWN.")
            sections.append(
                OnboardingSection(
                    title="Entry Points",
                    content="UNKNOWN: No entry points were supplied.",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            )

        # ── 3. Major components ──────────────────────────────────────────
        major_components = list(context.modules)
        if major_components:
            for mod in major_components:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.FILE,
                        description=f"Module: {mod}",
                    )
                )
            sections.append(
                OnboardingSection(
                    title="Major Components",
                    content=", ".join(major_components),
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
        else:
            limitations.append("No modules were supplied; major component identification is UNKNOWN.")
            sections.append(
                OnboardingSection(
                    title="Major Components",
                    content="UNKNOWN: No module information was supplied.",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            )

        # ── 4. Important files ───────────────────────────────────────────
        important_files = list(context.files)
        if important_files:
            for fp in important_files:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.FILE,
                        file_path=fp,
                        description=f"Important file: {fp}",
                    )
                )
            sections.append(
                OnboardingSection(
                    title="Important Files",
                    content=", ".join(important_files),
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
        else:
            limitations.append("No important files were supplied.")
            sections.append(
                OnboardingSection(
                    title="Important Files",
                    content="UNKNOWN: No file information was supplied.",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            )

        # ── 5. Development flow ──────────────────────────────────────────
        development_flow, flow_confidence = self._build_dev_flow(context, evidence)
        sections.append(
            OnboardingSection(
                title="Development Flow",
                content=development_flow,
                confidence=flow_confidence,
            )
        )
        if flow_confidence == ConfidenceLevel.UNKNOWN:
            limitations.append(
                "No development commands were supplied; typical development flow is UNKNOWN."
            )

        # ── 6. Documentation references ──────────────────────────────────
        doc_refs: list[str] = []
        if context.documentation:
            doc_refs.append("Project documentation supplied.")
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description="Project documentation supplied in context.",
                )
            )
            sections.append(
                OnboardingSection(
                    title="Documentation",
                    content=context.documentation[:500].strip()
                    + ("..." if len(context.documentation) > 500 else ""),
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
        else:
            limitations.append("No documentation was supplied.")
            sections.append(
                OnboardingSection(
                    title="Documentation",
                    content="UNKNOWN: No documentation was supplied.",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            )

        # ── 7. Test references ───────────────────────────────────────────
        test_refs = list(context.tests)
        if test_refs:
            for t in test_refs:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.TEST,
                        description=f"Test: {t}",
                    )
                )
            sections.append(
                OnboardingSection(
                    title="Tests",
                    content=", ".join(test_refs),
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
        else:
            limitations.append("No test information was supplied.")
            sections.append(
                OnboardingSection(
                    title="Tests",
                    content="UNKNOWN: No test information was supplied.",
                    confidence=ConfidenceLevel.UNKNOWN,
                )
            )

        # ── 8. Suggested starting points ─────────────────────────────────
        starting_points = self._build_starting_points(context)
        sections.append(
            OnboardingSection(
                title="Suggested Starting Points",
                content="\n".join(f"- {p}" for p in starting_points)
                if starting_points
                else "UNKNOWN: Insufficient context to suggest starting points.",
                confidence=ConfidenceLevel.CONFIRMED
                if starting_points
                else ConfidenceLevel.UNKNOWN,
            )
        )

        # ── Confidence ───────────────────────────────────────────────────
        confidence = self._build_confidence(context, evidence)

        return OnboardingResult(
            project_overview=project_overview,
            entry_points=entry_points,
            major_components=major_components,
            important_files=important_files,
            development_flow=development_flow,
            documentation_references=doc_refs,
            test_references=test_refs,
            suggested_starting_points=starting_points,
            sections=sections,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_overview(
        context: OnboardingContext,
        evidence: list[EvidenceItem],
    ) -> tuple[str, ConfidenceLevel]:
        """Build the project overview from the supplied context."""
        parts: list[str] = []

        if context.project_name:
            parts.append(f"Project: {context.project_name}.")
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description=f"Project name: {context.project_name}",
                )
            )

        if context.project_description:
            parts.append(context.project_description)
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description="Project description from supplied context.",
                )
            )

        if context.language:
            parts.append(f"Primary language: {context.language}.")

        if context.dependencies:
            parts.append(f"Known dependencies: {', '.join(context.dependencies)}.")

        if parts:
            return " ".join(parts), ConfidenceLevel.CONFIRMED

        # Try documentation
        if context.documentation:
            excerpt = context.documentation.strip()[:300]
            return excerpt, ConfidenceLevel.INFERRED

        return (
            "UNKNOWN: No project description, name, or documentation was supplied.",
            ConfidenceLevel.UNKNOWN,
        )

    @staticmethod
    def _build_dev_flow(
        context: OnboardingContext,
        evidence: list[EvidenceItem],
    ) -> tuple[str, ConfidenceLevel]:
        """Build a development flow description from supplied commands."""
        if not context.development_commands:
            return (
                "UNKNOWN: No development commands were supplied.",
                ConfidenceLevel.UNKNOWN,
            )

        lines: list[str] = []
        for cmd_name, cmd_value in context.development_commands.items():
            lines.append(f"{cmd_name}: {cmd_value}")
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.DOCUMENTATION,
                    description=f"Development command '{cmd_name}': {cmd_value}",
                )
            )

        return "Development commands: " + "; ".join(lines) + ".", ConfidenceLevel.CONFIRMED

    @staticmethod
    def _build_starting_points(context: OnboardingContext) -> list[str]:
        """Suggest starting points based on available context."""
        suggestions: list[str] = []

        if context.documentation:
            suggestions.append("Read the supplied project documentation.")

        if context.entry_points:
            first = context.entry_points[0]
            suggestions.append(f"Review the primary entry point: {first}")

        if context.modules:
            suggestions.append(
                f"Explore the main module(s): {', '.join(context.modules[:3])}"
                + (" ..." if len(context.modules) > 3 else "")
            )

        if context.tests:
            suggestions.append(
                "Run the test suite to verify the setup."
                if context.development_commands.get("test")
                else f"Locate the tests: {', '.join(context.tests[:3])}"
            )

        if context.development_commands:
            for cmd_name in ("install", "build", "setup"):
                if cmd_name in context.development_commands:
                    suggestions.append(
                        f"Run the {cmd_name} command: "
                        f"{context.development_commands[cmd_name]}"
                    )

        return suggestions

    @staticmethod
    def _build_confidence(
        context: OnboardingContext,
        evidence: list[EvidenceItem],
    ) -> ResponseConfidence:
        """Build overall confidence from accumulated evidence."""
        has_context = bool(
            context.project_name
            or context.project_description
            or context.modules
            or context.files
            or context.entry_points
            or context.documentation
        )

        if not has_context:
            return ResponseConfidence.unknown(
                notes="No repository context supplied; all aspects are UNKNOWN."
            )

        if evidence:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes="Onboarding result derived directly from supplied repository context.",
            )

        return ResponseConfidence.unknown(
            notes="Context supplied but no evidence items could be built."
        )
