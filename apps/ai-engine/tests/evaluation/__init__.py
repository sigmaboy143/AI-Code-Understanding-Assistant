"""AI evaluation tests for the AI Engine.

Category
--------
**Evaluation.** These tests judge output *quality* — is the answer usable, is
it grounded, is the confidence earned, is the evidence traceable — rather than
correctness of implementation, which the integration suite covers.

Files
-----
``test_ai_output_quality``
    The seven grounded-output invariants: non-empty answers, no fabricated
    repository facts, grounded dependencies, honest confidence, traceable
    evidence, and reproducible structured output.

Test categorisation across the suite
------------------------------------
============================  =========================================
Location                       Category
============================  =========================================
``tests/test_*.py``            unit — existing, deliberately unmoved
``tests/integration/``         integration — component boundaries
``tests/evaluation/``          evaluation — output quality invariants
``tests/fixtures/``            support code, collects nothing
============================  =========================================

No live LLM
------------
Every evaluation test substitutes a deterministic provider.  This keeps the
suite fast and reproducible, and it deliberately means these tests evaluate the
engine's grounding and honesty logic rather than the prose quality of any
particular model.  Live-model evaluation is a separate concern because it is not
reproducible and cannot gate a commit.
"""
