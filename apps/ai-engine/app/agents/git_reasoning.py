"""WHY / Git Reasoning Agent (Task 12).

Purpose
-------
Explain documented reasons for code changes using ONLY the Git context
that is explicitly supplied by the caller.  The agent reasons over commit
messages, diffs, issue text, PR text, and before/after code to explain
*why* a change was made.

The agent:
- Explains reasons documented directly in the supplied Git context.
- Distinguishes direct evidence (CONFIRMED) from inference (INFERRED).
- Returns UNKNOWN when the supplied context does not establish why a
  change happened.

The agent NEVER:
- Fabricates commits, authors, dates, PRs, issues, motives, or historical events.
- Scans the repository.
- Builds a Git parser.
- Assumes any context not explicitly supplied.

Input context
-------------
``GitContext`` may contain:
- commit_hash    — the commit SHA under investigation
- commit_message — the commit message text
- diff           — the raw diff text
- changed_files  — list of changed file paths
- issue_text     — linked issue description
- pr_text        — linked PR description
- code_before    — code before the change
- code_after     — code after the change
- related_context — any other relevant supplied context text

Confidence rules
----------------
CONFIRMED:
    The reason is directly stated in the commit message, PR text, or issue text.

INFERRED:
    The reason is a plausible conclusion reasoned from the diff, code changes,
    or other structural evidence — not explicitly stated.

UNKNOWN:
    Insufficient evidence to establish why the change was made.

Limitations
-----------
- Git context is supplied externally; the agent performs no Git operations.
- The agent cannot infer author intent beyond what is documented.
- Multi-commit histories are not reconstructed.
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


class GitContext(BaseModel):
    """Structured Git context supplied by the caller.

    All fields are optional.  When fields are absent the agent marks
    the corresponding aspects as UNKNOWN rather than fabricating data.
    """

    model_config = ConfigDict(extra="forbid")

    commit_hash: str | None = Field(
        default=None,
        description="The commit SHA being investigated.",
    )
    commit_message: str | None = Field(
        default=None,
        description="The commit message text.",
    )
    diff: str | None = Field(
        default=None,
        description="The raw diff text of the change.",
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="List of changed file paths.",
    )
    issue_text: str | None = Field(
        default=None,
        description="Linked issue description, if supplied.",
    )
    pr_text: str | None = Field(
        default=None,
        description="Linked PR description, if supplied.",
    )
    code_before: str | None = Field(
        default=None,
        description="The code before the change.",
    )
    code_after: str | None = Field(
        default=None,
        description="The code after the change.",
    )
    related_context: str | None = Field(
        default=None,
        description="Any other relevant context supplied by the caller.",
    )


# ---------------------------------------------------------------------------
# Output result models
# ---------------------------------------------------------------------------


class ReasoningStep(BaseModel):
    """A single step in the documented or inferred reasoning chain."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(
        description="Where this step came from, e.g. 'commit_message', 'diff', 'inferred'."
    )
    description: str = Field(description="What this step contributes to the explanation.")
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.CONFIRMED,
        description="Confidence level for this reasoning step.",
    )


class GitReasoningResult(BaseModel):
    """Structured output of the WHY/Git Reasoning Agent.

    Fields
    ------
    why_summary:
        Plain-language explanation of why the change was made.
        Set to 'UNKNOWN' when evidence is insufficient.
    documented_reasons:
        Reasons that are directly stated in the supplied Git context.
    inferred_reasons:
        Reasons that are inferred from the supplied diff/code changes.
    reasoning_chain:
        Ordered steps showing how the conclusion was reached.
    limitations:
        What the agent cannot determine from the supplied context.
    confidence:
        Overall confidence backed by evidence.
    """

    model_config = ConfigDict(extra="forbid")

    why_summary: str = Field(
        description="Why the change was made, or UNKNOWN if undeterminable."
    )
    documented_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons directly stated in commit message, PR, or issue.",
    )
    inferred_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons inferred from diff or code structure.",
    )
    reasoning_chain: list[ReasoningStep] = Field(
        default_factory=list,
        description="Ordered reasoning steps with evidence attribution.",
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


class GitReasoningAgent:
    """Reasons over supplied Git context to explain why a change was made.

    The agent is stateless.  Every call to ``analyse`` is independent.
    No Git operations, file-system access, or LLM calls are performed.

    Usage::

        agent = GitReasoningAgent()
        ctx = GitContext(
            commit_message="Fix: handle None input in process()",
            diff="- if value:\\n+ if value is not None:",
        )
        result = agent.analyse(ctx)
    """

    def analyse(self, context: GitContext) -> GitReasoningResult:
        """Produce a ``GitReasoningResult`` from the supplied Git context.

        Rules
        -----
        - Only use information present in *context*.
        - Mark aspects UNKNOWN when the required context is absent.
        - Never fabricate commits, authors, dates, PRs, issues, or motives.
        - Distinguish CONFIRMED (directly stated) from INFERRED (reasoned).

        Parameters
        ----------
        context:
            Structured Git context supplied by the caller.

        Returns
        -------
        GitReasoningResult
            Deterministic result derived exclusively from the supplied context.
        """
        # Check if any useful context was supplied at all
        if not self._has_any_context(context):
            return GitReasoningResult(
                why_summary="UNKNOWN: No Git context was supplied.",
                limitations=[
                    "No Git context was supplied. Supply at least one of: "
                    "commit_message, diff, issue_text, pr_text, code_before/code_after, "
                    "or related_context."
                ],
                confidence=ResponseConfidence.unknown(
                    notes="No Git context supplied; reason is UNKNOWN."
                ),
            )

        evidence: list[EvidenceItem] = []
        documented_reasons: list[str] = []
        inferred_reasons: list[str] = []
        reasoning_chain: list[ReasoningStep] = []
        limitations: list[str] = []

        # ── Extract documented reasons from commit message ───────────────
        if context.commit_message:
            reason = context.commit_message.strip()
            documented_reasons.append(f"Commit message: {reason}")
            reasoning_chain.append(
                ReasoningStep(
                    source="commit_message",
                    description=f"Commit message states: {reason}",
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.GIT_COMMIT,
                    description=f"Commit message: {reason[:120]}",
                )
            )

        # ── Extract documented reasons from issue text ───────────────────
        if context.issue_text:
            issue_summary = context.issue_text.strip()[:200]
            documented_reasons.append(f"Linked issue: {issue_summary}")
            reasoning_chain.append(
                ReasoningStep(
                    source="issue_text",
                    description=f"Linked issue context: {issue_summary}",
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.GIT_COMMIT,
                    description=f"Linked issue text supplied.",
                )
            )

        # ── Extract documented reasons from PR text ──────────────────────
        if context.pr_text:
            pr_summary = context.pr_text.strip()[:200]
            documented_reasons.append(f"PR description: {pr_summary}")
            reasoning_chain.append(
                ReasoningStep(
                    source="pr_text",
                    description=f"PR description: {pr_summary}",
                    confidence=ConfidenceLevel.CONFIRMED,
                )
            )
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.GIT_COMMIT,
                    description="PR description supplied.",
                )
            )

        # ── Infer reasons from diff ──────────────────────────────────────
        if context.diff:
            diff_inferences = self._infer_from_diff(context.diff)
            for inference in diff_inferences:
                inferred_reasons.append(inference)
                reasoning_chain.append(
                    ReasoningStep(
                        source="diff",
                        description=inference,
                        confidence=ConfidenceLevel.INFERRED,
                    )
                )
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.SOURCE_CODE,
                    description="Diff text supplied.",
                )
            )

        # ── Infer reasons from code_before / code_after ──────────────────
        if context.code_before is not None and context.code_after is not None:
            change_inferences = self._infer_from_code_change(
                context.code_before, context.code_after
            )
            for inference in change_inferences:
                inferred_reasons.append(inference)
                reasoning_chain.append(
                    ReasoningStep(
                        source="code_change",
                        description=inference,
                        confidence=ConfidenceLevel.INFERRED,
                    )
                )
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.SOURCE_CODE,
                    description="Code before/after supplied.",
                )
            )
        elif context.code_before is not None or context.code_after is not None:
            # Only one side supplied — still useful
            side = "code_before" if context.code_before else "code_after"
            limitations.append(
                f"Only {side} was supplied; full change analysis requires both "
                "code_before and code_after."
            )

        # ── Related context ──────────────────────────────────────────────
        if context.related_context:
            reasoning_chain.append(
                ReasoningStep(
                    source="related_context",
                    description=f"Additional context: {context.related_context[:150]}",
                    confidence=ConfidenceLevel.INFERRED,
                )
            )
            inferred_reasons.append(
                f"Additional context supplied: {context.related_context[:150]}"
            )

        # ── Changed files ────────────────────────────────────────────────
        if context.changed_files:
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.FILE,
                    description=f"Changed files: {', '.join(context.changed_files[:5])}",
                )
            )

        # ── Limitations ──────────────────────────────────────────────────
        if not documented_reasons:
            limitations.append(
                "No commit message, PR description, or issue text was supplied; "
                "no directly documented reason is available."
            )
        if not context.diff and not context.code_before and not context.code_after:
            limitations.append(
                "No diff or code change was supplied; structural change inference "
                "is UNKNOWN."
            )

        # ── Build the summary and confidence ─────────────────────────────
        why_summary = self._build_summary(
            documented_reasons, inferred_reasons, context
        )
        confidence = self._build_confidence(
            evidence, documented_reasons, inferred_reasons
        )

        return GitReasoningResult(
            why_summary=why_summary,
            documented_reasons=documented_reasons,
            inferred_reasons=inferred_reasons,
            reasoning_chain=reasoning_chain,
            limitations=limitations,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_any_context(context: GitContext) -> bool:
        """Return True if at least one useful Git-context field is present."""
        return bool(
            context.commit_message
            or context.diff
            or context.changed_files
            or context.issue_text
            or context.pr_text
            or context.code_before
            or context.code_after
            or context.related_context
        )

    @staticmethod
    def _infer_from_diff(diff: str) -> list[str]:
        """Infer change characteristics from a raw diff string.

        Only describes what is structurally visible in the diff.
        Never fabricates reasons.
        """
        inferences: list[str] = []
        lines = diff.splitlines()
        additions = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        deletions = [l for l in lines if l.startswith("-") and not l.startswith("---")]

        if additions and not deletions:
            inferences.append(
                f"Change adds {len(additions)} line(s) with no deletions "
                "(INFERRED: likely an addition of new functionality)."
            )
        elif deletions and not additions:
            inferences.append(
                f"Change removes {len(deletions)} line(s) with no additions "
                "(INFERRED: likely a removal or cleanup)."
            )
        elif additions and deletions:
            inferences.append(
                f"Change modifies code: {len(additions)} line(s) added, "
                f"{len(deletions)} line(s) removed "
                "(INFERRED: likely a modification of existing behaviour)."
            )

        # Look for common patterns in added lines
        added_text = " ".join(additions).lower()
        if "fix" in added_text or "bug" in added_text:
            inferences.append(
                "INFERRED: Diff content mentions 'fix' or 'bug'; change may be a bug fix."
            )
        if "test" in added_text:
            inferences.append(
                "INFERRED: Diff includes test-related additions."
            )
        if "deprecat" in added_text or "remov" in added_text:
            inferences.append(
                "INFERRED: Diff content suggests deprecation or removal."
            )

        return inferences

    @staticmethod
    def _infer_from_code_change(before: str, after: str) -> list[str]:
        """Infer change characteristics by comparing before/after code."""
        inferences: list[str] = []

        before_lines = before.splitlines()
        after_lines = after.splitlines()

        added = len(after_lines) - len(before_lines)
        if added > 0:
            inferences.append(
                f"Code grew by approximately {added} line(s) "
                "(INFERRED: new logic or content was added)."
            )
        elif added < 0:
            inferences.append(
                f"Code shrank by approximately {abs(added)} line(s) "
                "(INFERRED: logic or content was removed)."
            )
        else:
            inferences.append(
                "Code line count is unchanged (INFERRED: in-place modification)."
            )

        # Check for function signature changes (heuristic)
        before_defs = {
            l.strip()
            for l in before_lines
            if l.strip().startswith("def ") or l.strip().startswith("async def ")
        }
        after_defs = {
            l.strip()
            for l in after_lines
            if l.strip().startswith("def ") or l.strip().startswith("async def ")
        }
        new_defs = after_defs - before_defs
        removed_defs = before_defs - after_defs
        if new_defs:
            inferences.append(
                f"INFERRED: New function(s) added in code_after: "
                f"{', '.join(list(new_defs)[:3])}."
            )
        if removed_defs:
            inferences.append(
                f"INFERRED: Function(s) removed from code_before: "
                f"{', '.join(list(removed_defs)[:3])}."
            )

        return inferences

    @staticmethod
    def _build_summary(
        documented_reasons: list[str],
        inferred_reasons: list[str],
        context: GitContext,
    ) -> str:
        """Build the why_summary from collected reasons."""
        if documented_reasons:
            primary = documented_reasons[0]
            if len(documented_reasons) > 1:
                primary += f" (and {len(documented_reasons) - 1} additional documented reason(s))"
            return primary

        if inferred_reasons:
            return (
                "INFERRED (no direct documentation): "
                + inferred_reasons[0]
            )

        return "UNKNOWN: The supplied context does not establish why this change was made."

    @staticmethod
    def _build_confidence(
        evidence: list[EvidenceItem],
        documented_reasons: list[str],
        inferred_reasons: list[str],
    ) -> ResponseConfidence:
        """Determine the overall confidence level."""
        if not evidence:
            return ResponseConfidence.unknown(
                notes="No Git context evidence was supplied."
            )

        if documented_reasons:
            return ResponseConfidence(
                level=ConfidenceLevel.CONFIRMED,
                evidence=evidence,
                notes="Reason is directly stated in the supplied Git context.",
            )

        if inferred_reasons:
            return ResponseConfidence(
                level=ConfidenceLevel.INFERRED,
                evidence=evidence,
                notes=(
                    "Reason is inferred from the supplied diff/code change; "
                    "no directly documented reason was supplied."
                ),
            )

        return ResponseConfidence.unknown(
            notes="Git context was supplied but insufficient to determine the reason."
        )
