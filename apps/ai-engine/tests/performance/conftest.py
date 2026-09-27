"""Session hooks for the performance suite.

Prints the accumulated measurement table once the run finishes, so a recorded
run can be copied straight into a report.  Use ``-s`` to see it::

    python -m pytest apps/ai-engine/tests/performance -q -s

Nothing here affects pass/fail; the assertions live in the test modules.
"""

from __future__ import annotations

from tests.performance import harness


def pytest_sessionfinish(session, exitstatus) -> None:
    """Print the measurement table at the end of the performance run."""
    # Only for this directory, so a full-suite run does not bury the summary in
    # the middle of the rest of the output.
    collected = [
        item.nodeid
        for item in getattr(session, "items", [])
    ]
    if not any("/performance/" in nodeid.replace("\\", "/") for nodeid in collected):
        return
    harness.print_table()
