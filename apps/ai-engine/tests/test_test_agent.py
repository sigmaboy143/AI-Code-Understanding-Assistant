"""Tests for the Test Agent (Task 15B).

Coverage
--------
- Supplied test context produces test summaries
- Related test identification from target symbol/file
- Behavior explanation from descriptions
- Missing test information → UNKNOWN
- No fabricated coverage
- Evidence items reference supplied test context
- Confidence behaviour
- Question answering from test context
"""

from __future__ import annotations

from app.agents.test_agent import (
    TestAgent,
    SuiteContext as TestContext,
    SuiteAnalysisResult as TestResult,
)
from app.evidence.models import ConfidenceLevel, EvidenceSourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent() -> TestAgent:
    return TestAgent()


def _full_context() -> TestContext:
    return TestContext(
        test_names=[
            "test_login_success",
            "test_login_failure",
            "test_logout",
        ],
        test_code={
            "test_login_success": "def test_login_success():\n    assert login('user', 'pass') is True",
            "test_login_failure": "def test_login_failure():\n    assert login('user', 'wrong') is False",
        },
        test_descriptions={
            "test_login_success": "Verifies that valid credentials succeed.",
            "test_login_failure": "Verifies that invalid credentials are rejected.",
        },
        target_symbol="login",
        target_file="src/auth.py",
        coverage_info="85% line coverage for src/auth.py",
    )


# ---------------------------------------------------------------------------
# 1. Import test
# ---------------------------------------------------------------------------


def test_test_agent_can_be_imported():
    assert TestAgent is not None


def test_test_context_can_be_imported():
    assert TestContext is not None


def test_test_result_can_be_imported():
    assert TestResult is not None


# ---------------------------------------------------------------------------
# 2. Supplied test context produces summaries
# ---------------------------------------------------------------------------


def test_analyse_returns_test_result():
    result = _agent().analyse(_full_context())
    assert isinstance(result, TestResult)


def test_tests_from_test_names():
    ctx = TestContext(test_names=["test_foo", "test_bar"])
    result = _agent().analyse(ctx)
    names = [t.name for t in result.tests]
    assert "test_foo" in names
    assert "test_bar" in names


def test_tests_from_test_code():
    ctx = TestContext(test_code={"test_baz": "def test_baz(): pass"})
    result = _agent().analyse(ctx)
    names = [t.name for t in result.tests]
    assert "test_baz" in names


def test_tests_from_descriptions():
    ctx = TestContext(test_descriptions={"test_qux": "Tests the QUX feature."})
    result = _agent().analyse(ctx)
    names = [t.name for t in result.tests]
    assert "test_qux" in names


def test_test_has_description_when_supplied():
    result = _agent().analyse(_full_context())
    test_map = {t.name: t for t in result.tests}
    assert test_map["test_login_success"].description == "Verifies that valid credentials succeed."


def test_test_has_no_description_when_not_supplied():
    ctx = TestContext(test_names=["test_unknown"])
    result = _agent().analyse(ctx)
    test_map = {t.name: t for t in result.tests}
    assert test_map["test_unknown"].description is None


def test_test_has_code_flag():
    result = _agent().analyse(_full_context())
    test_map = {t.name: t for t in result.tests}
    assert test_map["test_login_success"].has_code is True
    assert test_map["test_logout"].has_code is False


def test_no_duplicate_test_summaries():
    """Tests that appear in both test_names and test_code are not duplicated."""
    ctx = TestContext(
        test_names=["test_foo"],
        test_code={"test_foo": "def test_foo(): pass"},
    )
    result = _agent().analyse(ctx)
    names = [t.name for t in result.tests]
    assert names.count("test_foo") == 1


# ---------------------------------------------------------------------------
# 3. Related test identification
# ---------------------------------------------------------------------------


def test_related_tests_found_by_symbol():
    result = _agent().analyse(_full_context())
    # "login" is the target_symbol — test_login_success and test_login_failure should match
    assert len(result.related_tests) >= 2
    assert "test_login_success" in result.related_tests
    assert "test_login_failure" in result.related_tests


def test_related_tests_not_fabricated():
    """Related tests must only be from the supplied test names."""
    result = _agent().analyse(_full_context())
    all_known = set(_full_context().test_names) | set(_full_context().test_code.keys())
    for related in result.related_tests:
        assert related in all_known


def test_no_related_tests_without_target():
    ctx = TestContext(test_names=["test_foo"])
    result = _agent().analyse(ctx)
    assert result.related_tests == []


def test_related_tests_by_code_content():
    ctx = TestContext(
        test_code={
            "test_auth_flow": "def test_auth_flow():\n    result = authenticate()\n    assert result",
        },
        target_symbol="authenticate",
    )
    result = _agent().analyse(ctx)
    assert "test_auth_flow" in result.related_tests


# ---------------------------------------------------------------------------
# 4. Behavior explanation
# ---------------------------------------------------------------------------


def test_overview_includes_test_count():
    result = _agent().analyse(_full_context())
    assert "3" in result.overview or "three" in result.overview.lower()


def test_overview_includes_target_symbol():
    result = _agent().analyse(_full_context())
    assert "login" in result.overview


def test_overview_includes_target_file():
    result = _agent().analyse(_full_context())
    assert "src/auth.py" in result.overview


def test_target_symbol_preserved():
    result = _agent().analyse(_full_context())
    assert result.target_symbol == "login"


def test_target_file_preserved():
    result = _agent().analyse(_full_context())
    assert result.target_file == "src/auth.py"


# ---------------------------------------------------------------------------
# 5. Missing test information → UNKNOWN
# ---------------------------------------------------------------------------


def test_empty_context_returns_unknown_overview():
    ctx = TestContext()
    result = _agent().analyse(ctx)
    assert "UNKNOWN" in result.overview


def test_empty_context_confidence_unknown():
    ctx = TestContext()
    result = _agent().analyse(ctx)
    assert result.confidence.level == ConfidenceLevel.UNKNOWN


def test_empty_context_limitations_present():
    ctx = TestContext()
    result = _agent().analyse(ctx)
    assert len(result.limitations) > 0


def test_missing_coverage_returns_unknown_coverage():
    ctx = TestContext(test_names=["test_foo"])
    result = _agent().analyse(ctx)
    assert "UNKNOWN" in result.coverage_summary


def test_missing_target_limitation():
    ctx = TestContext(test_names=["test_foo"])
    result = _agent().analyse(ctx)
    found = any("target" in lim.lower() or "symbol" in lim.lower() for lim in result.limitations)
    assert found


# ---------------------------------------------------------------------------
# 6. No fabricated coverage
# ---------------------------------------------------------------------------


def test_coverage_from_supplied_info():
    ctx = TestContext(
        test_names=["test_foo"],
        coverage_info="90% line coverage",
    )
    result = _agent().analyse(ctx)
    assert result.coverage_summary == "90% line coverage"


def test_no_invented_coverage():
    ctx = TestContext(test_names=["test_foo"])
    result = _agent().analyse(ctx)
    # Must say UNKNOWN, not invent a coverage number
    assert "UNKNOWN" in result.coverage_summary
    assert "%" not in result.coverage_summary


# ---------------------------------------------------------------------------
# 7. Evidence items
# ---------------------------------------------------------------------------


def test_evidence_source_type_is_test():
    result = _agent().analyse(_full_context())
    source_types = {e.source_type for e in result.confidence.evidence}
    assert EvidenceSourceType.TEST in source_types


def test_confirmed_confidence_with_tests():
    result = _agent().analyse(_full_context())
    assert result.confidence.level == ConfidenceLevel.CONFIRMED


def test_no_git_evidence_fabricated():
    result = _agent().analyse(_full_context())
    for ev in result.confidence.evidence:
        assert ev.source_type is not EvidenceSourceType.GIT_COMMIT


def test_evidence_count_matches_tests():
    ctx = TestContext(test_names=["test_a", "test_b"])
    result = _agent().analyse(ctx)
    # At least one evidence item per test
    assert len(result.confidence.evidence) >= 2


# ---------------------------------------------------------------------------
# 8. Question answering
# ---------------------------------------------------------------------------


def test_question_list_tests():
    ctx = TestContext(
        test_names=["test_foo", "test_bar"],
        question="What tests exist?",
    )
    result = _agent().analyse(ctx)
    assert result.answer is not None
    assert "test_foo" in result.answer


def test_question_what_does_verify():
    ctx = TestContext(
        test_descriptions={
            "test_login": "Verifies login works with valid credentials."
        },
        question="What does the test verify?",
    )
    result = _agent().analyse(ctx)
    assert result.answer is not None
    assert "login" in result.answer or "credentials" in result.answer


def test_question_coverage():
    ctx = TestContext(
        test_names=["test_foo"],
        coverage_info="95% branch coverage",
        question="What is the test coverage?",
    )
    result = _agent().analyse(ctx)
    assert result.answer is not None
    assert "95%" in result.answer


def test_question_coverage_unknown():
    ctx = TestContext(
        test_names=["test_foo"],
        question="What is the test coverage?",
    )
    result = _agent().analyse(ctx)
    assert result.answer is not None
    assert "UNKNOWN" in result.answer


def test_unanswerable_question_returns_unknown():
    ctx = TestContext(
        test_names=["test_foo"],
        question="What is the company stock price?",
    )
    result = _agent().analyse(ctx)
    assert result.answer is not None
    assert "UNKNOWN" in result.answer


def test_no_question_returns_none_answer():
    ctx = TestContext(test_names=["test_foo"])
    result = _agent().analyse(ctx)
    assert result.answer is None
