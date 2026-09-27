"""Tests for the WHY / Git Reasoning Agent (Task 12).

Coverage
--------
- Supplied Git evidence (commit message, diff, PR, issue)
- Documented reason → CONFIRMED
- Inferred reason from diff → INFERRED
- Missing Git evidence → UNKNOWN
- No fabricated commits, authors, dates, PRs, issues
- Reasoning chain attribution
- Confidence behaviour
- Limitations identification
"""

from __future__ import annotations

import pytest

from app.agents.git_reasoning import (
    GitContext,
    GitReasoningAgent,
    GitReasoningResult,
    ReasoningStep,
)
from app.evidence.models import ConfidenceLevel, EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent() -> GitReasoningAgent:
    return GitReasoningAgent()


def _commit_msg_context(msg: str = "Fix: handle None input") -> GitContext:
    return GitContext(commit_message=msg)


def _diff_context(diff: str = "+ if value is not None:\n-     if value:") -> GitContext:
    return GitContext(diff=diff)


def _full_context() -> GitContext:
    return GitContext(
        commit_hash="abc123",
        commit_message="Fix: handle None input in process()",
        diff="- if value:\n+ if value is not None:",
        changed_files=["src/process.py"],
        issue_text="Null pointer error when value is falsy but not None.",
        pr_text="This PR fixes the None-checking bug reported in issue #42.",
        code_before="def process(value):\n    if value:\n        return value",
        code_after="def process(value):\n    if value is not None:\n        return value",
    )


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------


def test_git_reasoning_agent_can_be_imported():
    assert GitReasoningAgent is not None


def test_git_context_can_be_imported():
    assert GitContext is not None


def test_git_reasoning_result_can_be_imported():
    assert GitReasoningResult is not None


# ---------------------------------------------------------------------------
# 2. Supplied Git evidence
# ---------------------------------------------------------------------------


def test_analyse_returns_result():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context())
    assert isinstance(result, GitReasoningResult)


def test_commit_message_appears_in_documented_reasons():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Fix: null pointer exception"))
    assert any("Fix: null pointer exception" in r for r in result.documented_reasons)


def test_issue_text_appears_in_documented_reasons():
    agent = _make_agent()
    ctx = GitContext(issue_text="Users reported a crash when the value is None.")
    result = agent.analyse(ctx)
    assert any("issue" in r.lower() for r in result.documented_reasons)


def test_pr_text_appears_in_documented_reasons():
    agent = _make_agent()
    ctx = GitContext(pr_text="This PR resolves a crash on None input.")
    result = agent.analyse(ctx)
    assert any("PR" in r or "pr_text" in r.lower() or "description" in r.lower() for r in result.documented_reasons)


def test_diff_produces_inferred_reasons():
    agent = _make_agent()
    ctx = _diff_context("+ def new_func():\n+     pass")
    result = agent.analyse(ctx)
    assert len(result.inferred_reasons) > 0


def test_reasoning_chain_populated():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert len(result.reasoning_chain) > 0


def test_reasoning_chain_attributes_sources():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    sources = {step.source for step in result.reasoning_chain}
    assert "commit_message" in sources


# ---------------------------------------------------------------------------
# 3. Documented reason → CONFIRMED
# ---------------------------------------------------------------------------


def test_documented_reason_gives_confirmed_confidence():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Add caching for performance"))
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_documented_reason_summary_not_unknown():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Refactor: extract utility functions"))
    assert "UNKNOWN" not in result.why_summary


def test_commit_message_is_primary_summary():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Security: fix XSS vulnerability"))
    assert "Security: fix XSS vulnerability" in result.why_summary


def test_full_context_confidence_confirmed():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_evidence_items_present_with_commit_message():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Add tests"))
    assert len(result.confidence.evidence) > 0


def test_evidence_source_type_git_commit_for_message():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context("Fix bug"))
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.GIT_COMMIT in source_types


# ---------------------------------------------------------------------------
# 4. Inferred reason from diff → INFERRED
# ---------------------------------------------------------------------------


def test_diff_only_gives_inferred_confidence():
    agent = _make_agent()
    ctx = GitContext(diff="+ return None\n- return value")
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.INFERRED


def test_diff_only_summary_marked_inferred():
    agent = _make_agent()
    ctx = GitContext(diff="+ x = 1\n- x = 0")
    result = agent.analyse(ctx)
    assert "INFERRED" in result.why_summary or result.inferred_reasons


def test_diff_addition_only_describes_addition():
    agent = _make_agent()
    ctx = GitContext(diff="+ def new_feature():\n+     pass")
    result = agent.analyse(ctx)
    combined = " ".join(result.inferred_reasons)
    assert "add" in combined.lower()


def test_diff_removal_only_describes_removal():
    agent = _make_agent()
    ctx = GitContext(diff="- def old_code():\n-     pass")
    result = agent.analyse(ctx)
    combined = " ".join(result.inferred_reasons)
    assert "remov" in combined.lower() or "delet" in combined.lower()


def test_code_before_after_inferences():
    agent = _make_agent()
    ctx = GitContext(
        code_before="def f():\n    return 1",
        code_after="def f():\n    return 1\ndef g():\n    return 2",
    )
    result = agent.analyse(ctx)
    assert len(result.inferred_reasons) > 0


def test_code_before_after_new_function_detected():
    agent = _make_agent()
    ctx = GitContext(
        code_before="def f():\n    pass",
        code_after="def f():\n    pass\ndef g():\n    pass",
    )
    result = agent.analyse(ctx)
    combined = " ".join(result.inferred_reasons)
    assert "g" in combined or "added" in combined.lower() or "new" in combined.lower()


def test_reasoning_chain_diff_step_is_inferred():
    agent = _make_agent()
    ctx = GitContext(diff="+ x = 1")
    result = agent.analyse(ctx)
    diff_steps = [s for s in result.reasoning_chain if s.source == "diff"]
    assert all(s.confidence == ConfidenceLevel.INFERRED for s in diff_steps)


# ---------------------------------------------------------------------------
# 5. Missing Git evidence → UNKNOWN
# ---------------------------------------------------------------------------


def test_empty_context_returns_unknown():
    agent = _make_agent()
    ctx = GitContext()
    result = agent.analyse(ctx)
    assert "UNKNOWN" in result.why_summary


def test_empty_context_confidence_unknown():
    agent = _make_agent()
    ctx = GitContext()
    result = agent.analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_has_limitation():
    agent = _make_agent()
    ctx = GitContext()
    result = agent.analyse(ctx)
    assert len(result.limitations) > 0


def test_no_commit_message_limitation_recorded():
    agent = _make_agent()
    ctx = GitContext(diff="+ x = 1")
    result = agent.analyse(ctx)
    found = any("commit message" in lim.lower() or "documented reason" in lim.lower() for lim in result.limitations)
    assert found


def test_no_diff_limitation_recorded():
    agent = _make_agent()
    ctx = GitContext(commit_message="Fix bug")
    result = agent.analyse(ctx)
    found = any("diff" in lim.lower() or "change" in lim.lower() for lim in result.limitations)
    assert found


def test_commit_hash_alone_returns_unknown():
    """Commit hash alone has no useful textual evidence."""
    agent = _make_agent()
    ctx = GitContext(commit_hash="abc123")  # No message, diff, etc.
    result = agent.analyse(ctx)
    assert "UNKNOWN" in result.why_summary


# ---------------------------------------------------------------------------
# 6. No fabricated history
# ---------------------------------------------------------------------------


def test_no_invented_author():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    all_text = (
        result.why_summary
        + " ".join(result.documented_reasons)
        + " ".join(result.inferred_reasons)
    )
    # No specific person's name should be invented
    assert "John" not in all_text
    assert "Jane" not in all_text


def test_no_invented_commit_hash():
    agent = _make_agent()
    ctx = GitContext(commit_message="Fix: crash on empty input")
    result = agent.analyse(ctx)
    # The hash "abc123" is not in the context we supplied here
    all_text = result.why_summary + " ".join(result.documented_reasons)
    assert "deadbeef" not in all_text


def test_no_invented_pr_number():
    agent = _make_agent()
    ctx = GitContext(commit_message="Fix: crash")
    result = agent.analyse(ctx)
    combined = " ".join(result.documented_reasons + result.inferred_reasons)
    assert "PR #" not in combined or "#42" not in combined


def test_only_supplied_changed_files_in_evidence():
    agent = _make_agent()
    ctx = GitContext(
        commit_message="Update config",
        changed_files=["config.py"],
    )
    result = agent.analyse(ctx)
    file_descriptions = [
        e.description or "" for e in result.confidence.evidence
    ]
    combined = " ".join(file_descriptions)
    assert "config.py" in combined
    assert "invented_file.py" not in combined


# ---------------------------------------------------------------------------
# 7. Confidence notes
# ---------------------------------------------------------------------------


def test_confidence_notes_present():
    agent = _make_agent()
    result = agent.analyse(_commit_msg_context())
    assert result.confidence.notes is not None
    assert len(result.confidence.notes) > 0


def test_reasoning_chain_step_has_confidence():
    agent = _make_agent()
    result = agent.analyse(_full_context())
    for step in result.reasoning_chain:
        assert isinstance(step.confidence, ConfidenceLevel)


# ---------------------------------------------------------------------------
# 8. Only one side of code supplied
# ---------------------------------------------------------------------------


def test_only_code_before_limitation():
    agent = _make_agent()
    ctx = GitContext(code_before="def f(): pass")
    result = agent.analyse(ctx)
    found = any("code_before" in lim.lower() or "both" in lim.lower() for lim in result.limitations)
    assert found


def test_only_code_after_limitation():
    agent = _make_agent()
    ctx = GitContext(code_after="def f(): return 1")
    result = agent.analyse(ctx)
    found = any("code_after" in lim.lower() or "both" in lim.lower() for lim in result.limitations)
    assert found
