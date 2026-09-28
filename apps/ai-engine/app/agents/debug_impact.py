"""Debug and Impact Analysis Agent (Task 13).

Purpose
-------
Two focused analysis capabilities:

A. DEBUG ANALYSIS
   Identify the likely failure location and root cause of an error using
   only the supplied error message, stack trace, source code, and retrieved
   context.

B. IMPACT ANALYSIS
   Identify directly and indirectly affected components when code changes,
   using only the supplied dependency/relationship context and test context.

Neither capability:
- Builds a dependency parser.
- Scans the repository or file system.
- Fabricates root causes, dependencies, or test results.
- Calls a real LLM (uses injected LLMProvider for debug text completion).

Evidence and confidence
-----------------------
CONFIRMED:
    Failure location or affected component is directly stated in the
    supplied stack trace, error message, or dependency context.

INFERRED:
    Likely cause or indirect impact is reasoned from the supplied evidence.

UNKNOWN:
    Insufficient evidence to determine root cause or impact.

Limitations
-----------
- Debug analysis is limited to what the supplied stack trace and code show.
- Impact analysis is limited to what the supplied relationship data shows.
- No AST parsing or execution is performed.
- Dependency relationships are supplied externally; none are inferred
  from source code unless explicitly provided.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.context_builder.builder import IncludedChunk
from app.evidence.models import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    ResponseConfidence,
)
from app.providers.base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from app.schemas.code_understanding import Severity


# ===========================================================================
# A. DEBUG ANALYSIS
# ===========================================================================

# ---------------------------------------------------------------------------
# Input context
# ---------------------------------------------------------------------------


class DebugContext(BaseModel):
    """Structured context for a debug analysis request.

    All fields except ``error_message`` are optional.  When fields are absent
    the agent returns UNKNOWN for the aspects that require them.
    """

    model_config = ConfigDict(extra="forbid")

    error_message: str = Field(
        description="The error or exception message (required)."
    )
    stack_trace: str | None = Field(
        default=None,
        description="The full stack trace text, if available.",
    )
    source_code: str | None = Field(
        default=None,
        description="Relevant source code where the error occurs.",
    )
    retrieved_chunks: list[IncludedChunk] = Field(
        default_factory=list,
        description="Retrieved context chunks pre-selected by the context builder.",
    )
    recent_changes: str | None = Field(
        default=None,
        description="Optional description of recent changes relevant to the error.",
    )
    file_path: str | None = Field(
        default=None,
        description="Repository-relative file path of the failing code.",
    )


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class DebugLocation(BaseModel):
    """A potential failure location identified from the supplied evidence."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        description="Where the failure is likely occurring."
    )
    file_path: str | None = Field(default=None)
    line: str | None = Field(
        default=None,
        description="Line reference from the stack trace, if available.",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.CONFIRMED,
        description="How confident we are in this location.",
    )


class DebugResult(BaseModel):
    """Structured output of the Debug Analysis capability.

    Fields
    ------
    error_summary:
        Short summary of the error being analysed.
    likely_locations:
        Where the failure is likely located, from stack trace / code evidence.
    root_cause:
        Likely root cause explanation.
        UNKNOWN when evidence is insufficient.
    investigation_steps:
        Suggested next investigation or fix direction.
    limitations:
        Aspects the agent cannot determine from the supplied context.
    confidence:
        Evidence-backed confidence for the result.
    """

    model_config = ConfigDict(extra="forbid")

    error_summary: str = Field(
        description="Short summary of the error."
    )
    likely_locations: list[DebugLocation] = Field(
        default_factory=list,
        description="Likely failure locations from stack trace / code evidence.",
    )
    root_cause: str = Field(
        description="Likely root cause, or UNKNOWN if evidence is insufficient."
    )
    investigation_steps: list[str] = Field(
        default_factory=list,
        description="Suggested next investigation or fix steps.",
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
# Debug Agent
# ---------------------------------------------------------------------------

_DEBUG_SYSTEM_PROMPT = """\
You are an expert software engineer performing focused debug analysis.

RULES — follow these strictly:
1. Base ALL answers ONLY on the error message, stack trace, and code supplied.
2. Do NOT invent root causes, dependencies, or code behaviour not visible in
   the supplied inputs.
3. If the root cause cannot be determined from the supplied information, say
   "UNKNOWN" and explain what additional context would help.
4. Suggest investigation steps based only on what is visible in the supplied
   evidence.
5. Be concise and precise.
"""


class DebugAgent:
    """Analyses an error using the supplied error, stack trace, and code.

    Usage::

        agent = DebugAgent(provider=mock_provider)
        result = await agent.analyse(context)

    When no provider is supplied the agent uses deterministic rules only.

    Parameters
    ----------
    provider:
        Any ``LLMProvider`` implementation.  Pass ``None`` to use the
        deterministic no-LLM mode.
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    async def analyse(self, context: DebugContext) -> DebugResult:
        """Produce a ``DebugResult`` from the supplied debug context.

        Parameters
        ----------
        context:
            Structured debug context supplied by the caller.

        Returns
        -------
        DebugResult
            Deterministic result derived from the supplied evidence.
        """
        evidence: list[EvidenceItem] = []
        limitations: list[str] = []

        # ── Record evidence from what was supplied ────────────────────────
        evidence.append(
            EvidenceItem(
                source_type=EvidenceSourceType.SOURCE_CODE,
                description=f"Error message: {context.error_message[:120]}",
                file_path=context.file_path,
            )
        )

        if context.stack_trace:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.SOURCE_CODE,
                    description="Stack trace supplied.",
                    file_path=context.file_path,
                )
            )

        if context.source_code:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.SOURCE_CODE,
                    description="Source code supplied.",
                    file_path=context.file_path,
                )
            )

        for chunk in context.retrieved_chunks:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.RETRIEVED_CHUNK,
                    file_path=chunk.file_path,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    chunk_id=chunk.chunk_id,
                    description=chunk.symbol or chunk.source_type,
                )
            )

        # ── Extract failure locations from stack trace ────────────────────
        locations = self._extract_locations(context)

        # ── Limitations ───────────────────────────────────────────────────
        if not context.stack_trace:
            limitations.append(
                "No stack trace was supplied; failure location identification "
                "is limited to the error message only."
            )
        if not context.source_code and not context.retrieved_chunks:
            limitations.append(
                "No source code or retrieved context was supplied; root cause "
                "analysis is limited to the error message and stack trace."
            )

        # ── LLM-backed root cause, or deterministic fallback ──────────────
        llm_text: str | None = None
        if self._provider is not None:
            llm_request = self._build_llm_request(context)
            llm_response: LLMResponse = await self._provider.complete(llm_request)
            llm_text = (llm_response.content or "").strip() or None
        else:
            limitations.append(
                "No LLM provider supplied; root cause is based on structural "
                "analysis of the error message and stack trace only."
            )

        root_cause = self._derive_root_cause(context, llm_text)
        investigation_steps = self._derive_investigation_steps(context, llm_text)
        confidence = self._build_confidence(evidence, context, llm_text)

        return DebugResult(
            error_summary=context.error_message[:200],
            likely_locations=locations,
            root_cause=root_cause,
            investigation_steps=investigation_steps,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_locations(context: DebugContext) -> list[DebugLocation]:
        """Extract failure locations from the supplied stack trace."""
        locations: list[DebugLocation] = []

        if context.stack_trace:
            lines = context.stack_trace.splitlines()
            for line in lines:
                stripped = line.strip()
                # Python-style: '  File "path/to/file.py", line 42, in func_name'
                if stripped.startswith('File "') and ", line " in stripped:
                    try:
                        parts = stripped.split('"')
                        file_ref = parts[1] if len(parts) > 1 else None
                        line_part = stripped.split(", line ")
                        line_num = line_part[1].split(",")[0].strip() if len(line_part) > 1 else None
                        locations.append(
                            DebugLocation(
                                description=stripped,
                                file_path=file_ref,
                                line=line_num,
                                confidence=ConfidenceLevel.CONFIRMED,
                            )
                        )
                    except (IndexError, ValueError):
                        locations.append(
                            DebugLocation(
                                description=stripped,
                                confidence=ConfidenceLevel.CONFIRMED,
                            )
                        )
                # Generic: lines containing "at " and ".py:" or ":line"
                elif ("at " in stripped and ".py:" in stripped):
                    locations.append(
                        DebugLocation(
                            description=stripped,
                            confidence=ConfidenceLevel.INFERRED,
                        )
                    )

            if not locations:
                # Record the error location from the file_path if supplied
                if context.file_path:
                    locations.append(
                        DebugLocation(
                            description=f"Error occurred in: {context.file_path}",
                            file_path=context.file_path,
                            confidence=ConfidenceLevel.INFERRED,
                        )
                    )

        return locations

    @staticmethod
    def _derive_root_cause(context: DebugContext, llm_text: str | None) -> str:
        """Derive root cause from LLM output or deterministic fallback."""
        if llm_text:
            return llm_text

        # Deterministic fallback: describe what the error message tells us
        msg = context.error_message.strip()

        # Common Python exception patterns
        lower = msg.lower()
        if "attributeerror" in lower:
            return (
                f"INFERRED: AttributeError suggests accessing an attribute on None "
                f"or an object that does not have it. Error: {msg[:200]}"
            )
        if "typeerror" in lower:
            return (
                f"INFERRED: TypeError suggests a type mismatch or incorrect argument "
                f"type. Error: {msg[:200]}"
            )
        if "keyerror" in lower:
            return (
                f"INFERRED: KeyError suggests a dict key is missing. Error: {msg[:200]}"
            )
        if "indexerror" in lower:
            return (
                f"INFERRED: IndexError suggests list index out of range. Error: {msg[:200]}"
            )
        if "importerror" in lower or "modulenotfounderror" in lower:
            return (
                f"INFERRED: Import error suggests a missing or misnamed module. "
                f"Error: {msg[:200]}"
            )
        if "valueerror" in lower:
            return (
                f"INFERRED: ValueError suggests an invalid value was passed. "
                f"Error: {msg[:200]}"
            )
        if "namenameerror" in lower or "nameerror" in lower:
            return (
                f"INFERRED: NameError suggests an undefined variable. Error: {msg[:200]}"
            )
        if not context.stack_trace and not context.source_code:
            return (
                f"UNKNOWN: Insufficient evidence. Only the error message was supplied: "
                f"{msg[:200]}"
            )

        return (
            f"INFERRED from error message: {msg[:200]}. "
            "Supply source code and stack trace for a more precise analysis."
        )

    @staticmethod
    def _derive_investigation_steps(
        context: DebugContext, llm_text: str | None
    ) -> list[str]:
        """Derive investigation steps from available evidence."""
        steps: list[str] = []

        if context.stack_trace:
            steps.append(
                "Review the innermost frame in the supplied stack trace for the "
                "exact line where the exception was raised."
            )
        if context.source_code:
            steps.append(
                "Inspect the supplied source code around the failing line."
            )
        if context.recent_changes:
            steps.append(
                "Review the recent changes supplied in context — the failure "
                "may be caused by a recently introduced change."
            )
        if not context.stack_trace:
            steps.append(
                "Obtain a full stack trace to identify the exact failure location."
            )
        if not context.source_code and not context.retrieved_chunks:
            steps.append(
                "Supply the relevant source code to enable root-cause analysis."
            )

        return steps

    @staticmethod
    def _build_llm_request(context: DebugContext) -> LLMRequest:
        """Build an LLMRequest for the debug analysis."""
        parts: list[str] = []

        parts.append(f"Error message:\n{context.error_message}")

        if context.stack_trace:
            parts.append(f"\nStack trace:\n{context.stack_trace}")

        if context.source_code:
            parts.append(f"\nRelevant source code:\n{context.source_code}")

        if context.retrieved_chunks:
            chunk_lines: list[str] = []
            for chunk in context.retrieved_chunks:
                header = f"[{chunk.source_type}] {chunk.file_path}"
                if chunk.symbol:
                    header += f" — {chunk.symbol}"
                chunk_lines.append(f"{header}\n{chunk.content}")
            parts.append(
                "\nRetrieved context:\n" + "\n\n".join(chunk_lines)
            )

        if context.recent_changes:
            parts.append(f"\nRecent changes:\n{context.recent_changes}")

        parts.append(
            "\nAnalyse the error above and provide:\n"
            "1. The likely root cause.\n"
            "2. The most likely failure location.\n"
            "3. Suggested investigation/fix steps.\n"
            "If information is insufficient, state UNKNOWN."
        )

        user_msg = LLMMessage(role="user", content="\n".join(parts))
        system_msg = LLMMessage(role="system", content=_DEBUG_SYSTEM_PROMPT)
        return LLMRequest(messages=[system_msg, user_msg])

    @staticmethod
    def _build_confidence(
        evidence: list[EvidenceItem],
        context: DebugContext,
        llm_text: str | None,
    ) -> ResponseConfidence:
        """Determine the overall confidence level for the debug result."""
        if not evidence:
            return ResponseConfidence.unknown(notes="No debug evidence available.")

        has_stack = bool(context.stack_trace)
        has_code = bool(context.source_code or context.retrieved_chunks)

        if has_stack and has_code:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes=(
                    "Debug analysis based on supplied stack trace and source code."
                ),
            )

        if has_stack or has_code:
            return ResponseConfidence(
                level=ConfidenceLevel.INFERRED,
                evidence=evidence,
                notes=(
                    "Debug analysis based on partial evidence "
                    f"(stack_trace={has_stack}, source_code={has_code})."
                ),
            )

        return ResponseConfidence(
            level=ConfidenceLevel.UNKNOWN,
            evidence=evidence,
            notes=(
                "Only the error message was supplied; root cause is UNKNOWN."
            ),
        )


# ===========================================================================
# B. IMPACT ANALYSIS
# ===========================================================================

# ---------------------------------------------------------------------------
# Input context
# ---------------------------------------------------------------------------


class ComponentRelationship(BaseModel):
    """A supplied dependency or call relationship between two components."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Component that depends on the target.")
    target: str = Field(description="Component being depended upon.")
    kind: str = Field(
        default="dependency",
        description="Relationship kind: 'dependency', 'import', 'calls', 'extends', etc.",
    )
    description: str | None = Field(default=None)


class ImpactContext(BaseModel):
    """Structured context for an impact analysis request.

    All fields except ``changed_component`` are optional.  When
    relationship data is absent the result will note that indirect
    impact is UNKNOWN.
    """

    model_config = ConfigDict(extra="forbid")

    changed_component: str = Field(
        description="The name of the changed/current component (required)."
    )
    changed_code: str | None = Field(
        default=None,
        description="The changed or current source code.",
    )
    relationships: list[ComponentRelationship] = Field(
        default_factory=list,
        description="Supplied dependency/relationship context for the changed component.",
    )
    test_names: list[str] = Field(
        default_factory=list,
        description="Supplied test names related to the changed component.",
    )
    test_file_paths: list[str] = Field(
        default_factory=list,
        description="Supplied test file paths related to the changed component.",
    )


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class AffectedComponent(BaseModel):
    """A component affected by the change."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Component name.")
    impact_kind: str = Field(
        description="How it is affected: 'direct', 'indirect', 'test'."
    )
    reason: str | None = Field(
        default=None,
        description="Why this component is affected.",
    )
    severity: Severity = Field(
        default=Severity.MEDIUM,
        description="Estimated impact severity.",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.CONFIRMED,
        description="Confidence level for this impact assessment.",
    )


class ImpactResult(BaseModel):
    """Structured output of the Impact Analysis capability.

    Fields
    ------
    changed_component:
        The component that was changed.
    directly_affected:
        Components with a direct dependency on the changed component
        (from supplied relationships).
    indirectly_affected:
        Components with transitive dependency on the changed component
        (from supplied relationships, one level only).
    related_tests:
        Tests related to the changed component (from supplied test context).
    impact_summary:
        Plain-language summary of the impact.
    limitations:
        What the agent cannot determine from the supplied context.
    confidence:
        Evidence-backed confidence for the result.
    """

    model_config = ConfigDict(extra="forbid")

    changed_component: str = Field(
        description="The component that was changed."
    )
    directly_affected: list[AffectedComponent] = Field(
        default_factory=list,
        description="Components directly depending on the changed component.",
    )
    indirectly_affected: list[AffectedComponent] = Field(
        default_factory=list,
        description="Components with transitive dependency (one level only).",
    )
    related_tests: list[str] = Field(
        default_factory=list,
        description="Test names related to the changed component.",
    )
    impact_summary: str = Field(
        description="Plain-language impact summary."
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
# Impact Agent
# ---------------------------------------------------------------------------


class ImpactAgent:
    """Identifies components affected by a change using supplied relationship data.

    The agent is stateless.  No dependency parsing or repository scanning
    is performed.  All relationship data must be supplied in the context.

    Usage::

        agent = ImpactAgent()
        ctx = ImpactContext(
            changed_component="UserService",
            relationships=[
                ComponentRelationship(source="AuthController", target="UserService"),
            ],
            test_names=["test_user_creation"],
        )
        result = agent.analyse(ctx)
    """

    def analyse(self, context: ImpactContext) -> ImpactResult:
        """Produce an ``ImpactResult`` from the supplied impact context.

        Parameters
        ----------
        context:
            Structured impact context supplied by the caller.

        Returns
        -------
        ImpactResult
            Deterministic result derived exclusively from the supplied context.
        """
        evidence: list[EvidenceItem] = []
        limitations: list[str] = []
        directly_affected: list[AffectedComponent] = []
        indirectly_affected: list[AffectedComponent] = []

        # Record the changed component as evidence
        evidence.append(
            EvidenceItem(
                source_type=EvidenceSourceType.SOURCE_CODE,
                description=f"Changed component: {context.changed_component}",
            )
        )

        if context.changed_code:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.SOURCE_CODE,
                    description="Changed source code supplied.",
                )
            )

        if not context.relationships:
            limitations.append(
                "No relationship/dependency data was supplied. "
                "Direct and indirect impact analysis is UNKNOWN. "
                "Supply ComponentRelationship objects to enable impact analysis."
            )
        else:
            # ── Direct impact: components that depend on changed_component ──
            directly_affected = self._find_direct(context)
            for comp in directly_affected:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.FILE,
                        description=(
                            f"Component '{comp.name}' directly depends on "
                            f"'{context.changed_component}'."
                        ),
                    )
                )

            # ── Indirect impact (one level of transitive relationships) ──────
            indirectly_affected = self._find_indirect(context, directly_affected)
            for comp in indirectly_affected:
                evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.FILE,
                        description=(
                            f"Component '{comp.name}' indirectly depends on "
                            f"'{context.changed_component}' (INFERRED: one transitive hop)."
                        ),
                    )
                )

            if not directly_affected:
                limitations.append(
                    f"No supplied relationships reference '{context.changed_component}' "
                    "as a dependency target; no direct dependants were found."
                )

        # ── Related tests ────────────────────────────────────────────────
        related_tests: list[str] = []
        if context.test_names:
            related_tests = list(context.test_names)
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.TEST,
                    description=(
                        f"Supplied test names: {', '.join(related_tests[:5])}"
                    ),
                )
            )
        elif context.test_file_paths:
            related_tests = list(context.test_file_paths)
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.TEST,
                    description=(
                        f"Supplied test file paths: {', '.join(related_tests[:5])}"
                    ),
                )
            )
        else:
            limitations.append(
                "No test names or test file paths were supplied; "
                "related tests are UNKNOWN."
            )

        # ── Build summary ────────────────────────────────────────────────
        impact_summary = self._build_summary(
            context, directly_affected, indirectly_affected, related_tests
        )
        confidence = self._build_confidence(evidence, context)

        return ImpactResult(
            changed_component=context.changed_component,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            related_tests=related_tests,
            impact_summary=impact_summary,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_direct(context: ImpactContext) -> list[AffectedComponent]:
        """Find components that directly depend on the changed component."""
        directly_affected: list[AffectedComponent] = []
        for rel in context.relationships:
            if rel.target == context.changed_component:
                directly_affected.append(
                    AffectedComponent(
                        name=rel.source,
                        impact_kind="direct",
                        reason=(
                            rel.description
                            or f"'{rel.source}' has a '{rel.kind}' relationship "
                            f"with '{context.changed_component}'."
                        ),
                        severity=Severity.HIGH,
                        confidence=ConfidenceLevel.CONFIRMED,
                    )
                )
        return directly_affected

    @staticmethod
    def _find_indirect(
        context: ImpactContext,
        direct: list[AffectedComponent],
    ) -> list[AffectedComponent]:
        """Find components one transitive hop away from the changed component.

        Only components that depend on a *direct* dependant are considered
        indirect.  Deeper transitive chains are not explored because the
        relationship data may not be complete.
        """
        direct_names = {comp.name for comp in direct}
        indirect: list[AffectedComponent] = []
        seen: set[str] = set()

        for rel in context.relationships:
            if rel.target in direct_names and rel.source not in direct_names:
                if rel.source not in seen and rel.source != context.changed_component:
                    seen.add(rel.source)
                    indirect.append(
                        AffectedComponent(
                            name=rel.source,
                            impact_kind="indirect",
                            reason=(
                                f"'{rel.source}' depends on '{rel.target}' which "
                                f"directly depends on '{context.changed_component}' "
                                "(INFERRED: one transitive hop)."
                            ),
                            severity=Severity.MEDIUM,
                            confidence=ConfidenceLevel.INFERRED,
                        )
                    )
        return indirect

    @staticmethod
    def _build_summary(
        context: ImpactContext,
        directly_affected: list[AffectedComponent],
        indirectly_affected: list[AffectedComponent],
        related_tests: list[str],
    ) -> str:
        """Build a plain-language impact summary."""
        if not directly_affected and not related_tests and not indirectly_affected:
            return (
                f"UNKNOWN: No supplied dependency data references "
                f"'{context.changed_component}' as a dependency target. "
                "Impact cannot be determined without relationship data."
            )

        parts: list[str] = [
            f"Changing '{context.changed_component}' affects:"
        ]
        if directly_affected:
            names = ", ".join(c.name for c in directly_affected[:5])
            parts.append(
                f"  Direct dependants ({len(directly_affected)}): {names}."
            )
        if indirectly_affected:
            names = ", ".join(c.name for c in indirectly_affected[:5])
            parts.append(
                f"  Indirect dependants ({len(indirectly_affected)}): {names} "
                "(INFERRED: one transitive hop)."
            )
        if related_tests:
            names = ", ".join(related_tests[:5])
            parts.append(f"  Related tests: {names}.")

        return "\n".join(parts)

    @staticmethod
    def _build_confidence(
        evidence: list[EvidenceItem],
        context: ImpactContext,
    ) -> ResponseConfidence:
        """Determine the overall confidence level for the impact result."""
        if not context.relationships and not context.test_names and not context.test_file_paths:
            return ResponseConfidence.unknown(
                notes=(
                    "No relationship or test data was supplied; impact is UNKNOWN. "
                    "Supply ComponentRelationship objects and test references to "
                    "enable impact analysis."
                )
            )

        if context.relationships:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes=(
                    "Impact analysis based on supplied relationship data. "
                    "Indirect impact is INFERRED (one transitive hop only)."
                ),
            )

        # Only tests supplied, no relationships
        return ResponseConfidence(
            level=ConfidenceLevel.INFERRED,
            evidence=evidence,
            notes=(
                "Only test context was supplied; component impact is UNKNOWN. "
                "Related tests are CONFIRMED from supplied test context."
            ),
        )
