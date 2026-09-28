"""Deterministic, safe fixtures shared by the integration and evaluation suites.

Purpose
-------
Every fixture in this package is:

- **Deterministic** — the same fixture always produces byte-identical input, so
  a failing assertion is always reproducible.
- **Safe** — source snippets are two to six lines of trivial, synthetic code
  (``def add(a, b): return a + b``).  No repository source, no credentials, no
  customer data, no confidential material is embedded anywhere in this package.
- **Offline** — nothing here opens a socket, spawns a process, or reads the
  filesystem.  No fixture requires a running Ollama instance or any other
  network dependency.

What is provided
----------------
``analysis_inputs``
    Valid ``CodeUnderstandingRequest`` payloads keyed by analysis intent:
    ``explanation``, ``error_explanation``, ``structure``, ``dependencies``,
    ``improvements``.
``provider_responses``
    Deterministic ``LLMResponse`` bodies (and deliberately wrong or malformed
    ones) used to stand in for a live LLM call.
``failing_providers``
    Providers that raise ``ProviderError`` for the error-mapping tests, plus a
    recording provider that captures the outbound prompt.
``grounding_inputs``
    Retrieved chunks, supplied context, and synthetic log output used to
    exercise evidence grounding.
``ollama_transport``
    Scripted HTTP transports for the *real* ``OllamaProvider``, so upstream
    failure conditions can be exercised without a socket.
``expected_outputs``
    Hand-written expectations — grounded dependency names, confidence levels,
    fabrication tripwires — used by the evaluation layer.

Test categorisation
-------------------
This package is **support code**, not a test module.  It contains no ``test_*``
functions, so pytest collects nothing from here.  It backs two test categories:

- ``tests/integration/`` — request/response contract and error-envelope checks.
- ``tests/evaluation/`` — AI quality checks (grounding, confidence honesty).
"""

from __future__ import annotations

from .analysis_inputs import (
    ALL_ANALYSES,
    DEPENDENCIES_SOURCE,
    ERROR_CONTEXT,
    ERROR_LOG,
    ERROR_SOURCE,
    IMPROVABLE_SOURCE,
    SIMPLE_FILE_PATH,
    SIMPLE_SOURCE,
    dependencies_input,
    error_explanation_input,
    explanation_input,
    improvements_input,
    structure_input,
)
from .expected_outputs import (
    CONFIDENCE_LEVELS,
    EXPECTED_CONFIRMED_LEVEL,
    EXPECTED_GROUNDED_DEPENDENCIES,
    EXPECTED_INFERRED_LEVEL,
    EXPECTED_UNKNOWN_LEVEL,
    EXPECTED_UNGROUNDED_DEPENDENCIES,
    FABRICATED_REPOSITORY_FACTS,
    PRODUCIBLE_EVIDENCE_SOURCE_TYPES,
    RESERVED_EVIDENCE_SOURCE_TYPES,
)
from .failing_providers import (
    RecordingProvider,
    empty_content_provider,
    malformed_body_provider,
    provider_error_provider,
    provider_timeout_provider,
    static_provider,
    whitespace_content_provider,
)
from .grounding_inputs import (
    EXTERNAL_CHUNK,
    INTERNAL_CHUNK,
    MALFORMED_CHUNK_CONTENT,
    chunk_list,
)
from .ollama_transport import (
    CHAT_URL,
    FIXTURE_MODEL,
    MODEL_NOT_FOUND_BODY,
    NO_CONTENT_BODY,
    NO_MESSAGE_BODY,
    NON_JSON_BODY,
    NULL_THINKING_OLLAMA_BODY,
    OLLAMA_TEST_BASE_URL,
    THINKING_ONLY_OLLAMA_BODY,
    THINKING_OLLAMA_BODY,
    VALID_OLLAMA_BODY,
    analysis_llm_request,
    connect_error,
    install_transport,
    install_upstream,
    ollama_provider,
)
from .provider_responses import (
    DEPENDENCY_CLAIM_TEXT,
    ERROR_EXPLANATION_TEXT,
    EXPLANATION_TEXT,
    GIT_FACT_CLAIM_TEXT,
    IMPROVEMENT_TEXT,
    ONBOARDING_QUESTION_TEXT,
    STRUCTURE_TEXT,
    UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT,
    WHITESPACE_TEXT,
)

__all__ = [
    # Source constants
    "ALL_ANALYSES",
    "DEPENDENCIES_SOURCE",
    "ERROR_CONTEXT",
    "ERROR_LOG",
    "ERROR_SOURCE",
    "IMPROVABLE_SOURCE",
    "SIMPLE_FILE_PATH",
    "SIMPLE_SOURCE",
    # Provider response text constants
    "DEPENDENCY_CLAIM_TEXT",
    "ERROR_EXPLANATION_TEXT",
    "EXPLANATION_TEXT",
    "GIT_FACT_CLAIM_TEXT",
    "IMPROVEMENT_TEXT",
    "ONBOARDING_QUESTION_TEXT",
    "STRUCTURE_TEXT",
    "UNSUPPORTED_RELATIONSHIP_CLAIM_TEXT",
    "WHITESPACE_TEXT",
    # Grounding inputs
    "EXTERNAL_CHUNK",
    "INTERNAL_CHUNK",
    "MALFORMED_CHUNK_CONTENT",
    "chunk_list",
    # Ollama transport
    "CHAT_URL",
    "FIXTURE_MODEL",
    "MODEL_NOT_FOUND_BODY",
    "NO_CONTENT_BODY",
    "NO_MESSAGE_BODY",
    "NON_JSON_BODY",
    "NULL_THINKING_OLLAMA_BODY",
    "OLLAMA_TEST_BASE_URL",
    "THINKING_ONLY_OLLAMA_BODY",
    "THINKING_OLLAMA_BODY",
    "VALID_OLLAMA_BODY",
    "analysis_llm_request",
    "connect_error",
    "install_transport",
    "install_upstream",
    "ollama_provider",
    # Expected outputs
    "CONFIDENCE_LEVELS",
    "EXPECTED_CONFIRMED_LEVEL",
    "EXPECTED_GROUNDED_DEPENDENCIES",
    "EXPECTED_INFERRED_LEVEL",
    "EXPECTED_UNKNOWN_LEVEL",
    "EXPECTED_UNGROUNDED_DEPENDENCIES",
    "FABRICATED_REPOSITORY_FACTS",
    "PRODUCIBLE_EVIDENCE_SOURCE_TYPES",
    "RESERVED_EVIDENCE_SOURCE_TYPES",
    # Request builders
    "dependencies_input",
    "error_explanation_input",
    "explanation_input",
    "improvements_input",
    "structure_input",
    # Provider factories
    "RecordingProvider",
    "empty_content_provider",
    "malformed_body_provider",
    "provider_error_provider",
    "provider_timeout_provider",
    "static_provider",
    "whitespace_content_provider",
]
