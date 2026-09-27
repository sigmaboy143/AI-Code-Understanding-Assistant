"""Integration tests for the AI Engine.

Category
--------
**Integration.** Each module here drives a real component boundary — the HTTP
application, the orchestrator, the Ollama provider's transport — and replaces
only the outermost network hop with a deterministic fixture from
``tests.fixtures``.

Scope of this package
---------------------
``test_request_contract``
    The request half of the public contract: what the HTTP boundary accepts and
    what the engine actually forwards to the provider.
``test_response_contract``
    The response half: the success envelope, the error envelope, and
    confidentiality of error bodies.
``test_health_contract``
    ``/health`` and ``/ready`` as seen by Member 1's NestJS backend.
``test_provider_error_handling``
    How upstream Ollama conditions become ``ProviderError`` messages, which is
    what makes the 502-versus-504 mapping possible.
``test_confidence_evidence_mapping``
    Confidence determination and evidence attribution through the orchestrator.
``test_dependency_grounding_api``
    Dependency grounding as observed over HTTP.

Boundary
--------
No test in this package requires a running Ollama instance, a network
connection, or an LLM.  The live end-to-end path is not reproducible on CI
hardware and is therefore verified separately; see the Phase 13 report.

Not collected here
------------------
Unit tests remain in ``apps/ai-engine/tests/test_*.py`` and are deliberately not
moved.  AI-quality checks live in ``tests/evaluation/``.
"""
