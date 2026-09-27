"""Performance testing for the AI Engine.

This package holds the AI-side performance suite.  See :mod:`harness` for what is
and is not measured, and ``docs/ai-performance-report.md`` for the recorded
results of an actual run.

Layout
------
``harness``
    Timing primitives, sample counts, and thresholds.  Support code, not tests.
``test_provider_performance``
    Provider round-trip cost and retry behaviour.
``test_request_performance``
    Full in-process request cost and stage decomposition.
``test_timeout_performance``
    Real loopback timeout enforcement and the 504 mapping.
"""
