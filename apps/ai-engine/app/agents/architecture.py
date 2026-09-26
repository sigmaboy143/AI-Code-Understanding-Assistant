"""Architecture Agent (Task 14).

Purpose
-------
Explain the architecture of a repository using ONLY the structured
repository-intelligence context that is supplied to the agent.  The agent
never scans the repository itself, never runs an AST parser, and never
invents dependencies, services, APIs, data flows, or architecture boundaries
that are not present in the supplied context.

Input context
-------------
The agent accepts an ``ArchitectureContext`` that may contain:
- modules          — named modules/packages with optional descriptions
- files            — important files with optional roles
- symbols          — key symbols (classes, functions) and their locations
- imports          — import relationships between files/modules
- relationships    — explicit dependency or call-graph edges
- services         — named services and optional descriptions
- apis             — API surface definitions
- documentation    — any architecture documentation supplied by the caller
- entry_points     — known entry points into the system

Evidence and confidence
-----------------------
- CONFIRMED: claim is directly supported by a supplied field
- INFERRED:  claim is a plausible conclusion from supplied fields
- UNKNOWN:   required information is absent from the supplied context

Limitations
-----------
- The agent does not scan the file system.
- The agent does not parse source code or build dependency graphs.
- The agent does not call any LLM; it produces a structured result from
  the supplied context using deterministic rules.
- All facts in the result are traceable to the supplied ``ArchitectureContext``.
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


class ModuleInfo(BaseModel):
    """A module or package that is part of the architecture."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Module or package name.")
    description: str | None = Field(default=None, description="Optional role description.")
    files: list[str] = Field(default_factory=list, description="Files belonging to this module.")


class RelationshipInfo(BaseModel):
    """A directed dependency or call relationship between two components."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Component that depends on or calls the target.")
    target: str = Field(description="Component being depended upon or called.")
    kind: str = Field(
        default="dependency",
        description="Relationship kind, e.g. 'dependency', 'import', 'calls', 'extends'.",
    )
    description: str | None = Field(default=None)


class ServiceInfo(BaseModel):
    """A named service in the architecture."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Service name.")
    description: str | None = Field(default=None)
    endpoints: list[str] = Field(default_factory=list, description="Known API endpoints.")


class ArchitectureContext(BaseModel):
    """Structured repository-intelligence context for architecture analysis.

    All fields are optional.  When fields are absent the agent marks the
    corresponding aspects of the result as UNKNOWN rather than inventing data.
    """

    model_config = ConfigDict(extra="forbid")

    modules: list[ModuleInfo] = Field(
        default_factory=list,
        description="Named modules/packages discovered by upstream intelligence.",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Important file paths.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Key symbol names (classes, functions) found by upstream analysis.",
    )
    imports: list[str] = Field(
        default_factory=list,
        description="Import statements or import relationships discovered upstream.",
    )
    relationships: list[RelationshipInfo] = Field(
        default_factory=list,
        description="Explicit dependency/call-graph edges from upstream analysis.",
    )
    services: list[ServiceInfo] = Field(
        default_factory=list,
        description="Named services in the system.",
    )
    apis: list[str] = Field(
        default_factory=list,
        description="API surface definitions or endpoint lists.",
    )
    documentation: str | None = Field(
        default=None,
        description="Architecture documentation supplied by the caller (README, ADRs, etc.).",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Known system entry points (e.g. main modules, CLI scripts).",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class ComponentSummary(BaseModel):
    """A identified architectural component and its role."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str = Field(
        description="Component kind, e.g. 'module', 'service', 'file', 'entry_point'."
    )
    description: str | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED


class DependencyEdge(BaseModel):
    """A dependency relationship extracted from the supplied context."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    kind: str = "dependency"
    description: str | None = None


class ArchitectureResult(BaseModel):
    """Structured output of the Architecture Agent.

    Fields
    ------
    overview:
        Short plain-language overview of the system architecture.
        UNKNOWN when no context is supplied.
    components:
        Major identified components, each annotated with a confidence level.
    entry_points:
        Known system entry points from the supplied context.
    dependency_relationships:
        Dependency edges extracted from the supplied context.
        Empty when no relationship data is supplied.
    data_flow_summary:
        Short description of data flow.  UNKNOWN when not inferable.
    limitations:
        Aspects the agent cannot determine from the supplied context.
    confidence:
        Overall response confidence backed by evidence.
    """

    model_config = ConfigDict(extra="forbid")

    overview: str = Field(
        description="High-level architecture overview, or UNKNOWN if context is insufficient."
    )
    components: list[ComponentSummary] = Field(default_factory=list)
    entry_points: list[str] = Field(
        default_factory=list,
        description="Entry points from the supplied context.",
    )
    dependency_relationships: list[DependencyEdge] = Field(default_factory=list)
    data_flow_summary: str | None = Field(
        default=None,
        description="Data flow summary, or None when not determinable.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="What the agent cannot determine from the supplied context.",
    )
    confidence: ResponseConfidence = Field(
        default_factory=ResponseConfidence.unknown,
        description="Evidence-backed confidence for this result.",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ArchitectureAgent:
    """Analyses repository architecture from supplied structured context.

    This agent is deliberately stateless.  Every call to ``analyse`` is
    independent.  No state is persisted between calls.

    Usage::

        agent = ArchitectureAgent()
        result = agent.analyse(context)
    """

    def analyse(self, context: ArchitectureContext) -> ArchitectureResult:
        """Produce an ``ArchitectureResult`` from the supplied context.

        Rules
        -----
        - Only use information present in *context*.
        - Mark aspects UNKNOWN when the required context is absent.
        - Never invent dependencies, services, data flows, or boundaries.
        - Build evidence items only from fields that are actually populated.

        Parameters
        ----------
        context:
            Structured repository-intelligence context supplied by the caller.

        Returns
        -------
        ArchitectureResult
            Deterministic result derived exclusively from the supplied context.
        """
        evidence: list[EvidenceItem] = []
        limitations: list[str] = []

        # ── Identify components ──────────────────────────────────────────────
        components = self._extract_components(context, evidence)

        # ── Entry points ────────────────────────────────────────────────────
        entry_points = list(context.entry_points)

        # ── Dependency relationships ─────────────────────────────────────────
        dependency_edges = self._extract_relationships(context)

        # ── Overview ────────────────────────────────────────────────────────
        overview = self._build_overview(context, components)

        # ── Data flow ───────────────────────────────────────────────────────
        data_flow = self._build_data_flow(context)

        # ── Limitations ──────────────────────────────────────────────────────
        limitations = self._identify_limitations(context)

        # ── Confidence ──────────────────────────────────────────────────────
        confidence = self._build_confidence(context, evidence)

        return ArchitectureResult(
            overview=overview,
            components=components,
            entry_points=entry_points,
            dependency_relationships=dependency_edges,
            data_flow_summary=data_flow,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_components(
        context: ArchitectureContext,
        evidence: list[EvidenceItem],
    ) -> list[ComponentSummary]:
        """Extract identified components from the supplied context."""
        components: list[ComponentSummary] = []

        for module in context.modules:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.FILE,
                    description=f"Module '{module.name}' from supplied context.",
                )
            )
            components.append(
                ComponentSummary(
                    name=module.name,
                    kind="module",
                    description=module.description,
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )

        for service in context.services:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.FILE,
                    description=f"Service '{service.name}' from supplied context.",
                )
            )
            components.append(
                ComponentSummary(
                    name=service.name,
                    kind="service",
                    description=service.description,
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )

        for file_path in context.files:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.FILE,
                    file_path=file_path,
                    description=f"File '{file_path}' from supplied context.",
                )
            )
            components.append(
                ComponentSummary(
                    name=file_path,
                    kind="file",
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )

        for entry in context.entry_points:
            components.append(
                ComponentSummary(
                    name=entry,
                    kind="entry_point",
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )

        return components

    @staticmethod
    def _extract_relationships(context: ArchitectureContext) -> list[DependencyEdge]:
        """Convert supplied relationship info into dependency edges."""
        return [
            DependencyEdge(
                source=rel.source,
                target=rel.target,
                kind=rel.kind,
                description=rel.description,
            )
            for rel in context.relationships
        ]

    @staticmethod
    def _build_overview(
        context: ArchitectureContext,
        components: list[ComponentSummary],
    ) -> str:
        """Build a plain-language overview from the available context."""
        # Use supplied documentation first
        if context.documentation:
            return context.documentation.strip()

        # Build from structured data
        if not components and not context.apis:
            return "UNKNOWN: No architecture context was supplied."

        parts: list[str] = []

        module_names = [c.name for c in components if c.kind == "module"]
        service_names = [c.name for c in components if c.kind == "service"]
        entry_names = [c.name for c in components if c.kind == "entry_point"]

        if module_names:
            parts.append(f"Modules: {', '.join(module_names)}.")
        if service_names:
            parts.append(f"Services: {', '.join(service_names)}.")
        if entry_names:
            parts.append(f"Entry points: {', '.join(entry_names)}.")
        if context.apis:
            parts.append(f"APIs: {', '.join(context.apis)}.")
        if context.relationships:
            parts.append(
                f"{len(context.relationships)} dependency relationship(s) supplied."
            )

        return " ".join(parts) if parts else "UNKNOWN: No architecture context was supplied."

    @staticmethod
    def _build_data_flow(context: ArchitectureContext) -> str | None:
        """Summarise data flow when relationship evidence exists."""
        if not context.relationships:
            return None
        edges = [f"{r.source} → {r.target}" for r in context.relationships[:5]]
        summary = "; ".join(edges)
        if len(context.relationships) > 5:
            summary += f" (and {len(context.relationships) - 5} more)"
        return summary

    @staticmethod
    def _identify_limitations(context: ArchitectureContext) -> list[str]:
        """Record what information is absent from the supplied context."""
        limitations: list[str] = []

        if not context.modules and not context.services and not context.files:
            limitations.append(
                "No modules, services, or files were supplied; "
                "component identification is UNKNOWN."
            )
        if not context.relationships and not context.imports:
            limitations.append(
                "No relationship or import data was supplied; "
                "dependency graph is UNKNOWN."
            )
        if not context.entry_points:
            limitations.append(
                "No entry points were supplied; entry-point identification is UNKNOWN."
            )
        if not context.documentation:
            limitations.append(
                "No architecture documentation was supplied; "
                "documented design rationale is UNKNOWN."
            )

        return limitations

    @staticmethod
    def _build_confidence(
        context: ArchitectureContext,
        evidence: list[EvidenceItem],
    ) -> ResponseConfidence:
        """Build a ``ResponseConfidence`` from the available evidence."""
        has_context = bool(
            context.modules
            or context.services
            or context.files
            or context.relationships
            or context.documentation
            or context.entry_points
            or context.apis
        )

        if not has_context:
            return ResponseConfidence.unknown(
                notes="No architecture context supplied; all aspects are UNKNOWN."
            )

        if evidence:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes="Architecture result derived directly from supplied context.",
            )

        return ResponseConfidence.unknown(
            notes="Context supplied but could not be mapped to specific evidence items."
        )
