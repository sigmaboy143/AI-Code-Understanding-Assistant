"""Contract-level integration tests: health and readiness endpoints.

Category
--------
**Integration.** Real FastAPI application via ``TestClient``.

Scope
-----
- ``GET /health``  — liveness, must answer 200 while the process is up
- ``GET /ready``   — readiness, 200 when configured, 503 with the standard
  error envelope when not

Why it exists
-------------
``GET /ready`` is the single endpoint Member 1's NestJS backend calls to decide
whether to report ``aiEngine=ok``.  If readiness ever returned 200 while the
engine could not actually serve a request, NestJS would advertise a healthy
dependency that cannot answer.  ``tests/test_api.py`` covers the same two
endpoints, so this file is deliberately limited to the *dependency-facing*
contract: the exact status codes, the exact body shapes, and the guarantee that
readiness makes **no** LLM call.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures import RecordingProvider

client = TestClient(app)


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------


def test_health_returns_200_and_ok_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_provider_configuration():
    """Liveness reports process state only; it must not depend on config."""
    with patch("app.main.settings") as settings:
        settings.is_configured = False

        response = client.get("/health")

    assert response.status_code == 200


def test_health_makes_no_provider_call():
    provider = RecordingProvider("unused")

    with patch("app.main._build_provider", return_value=provider):
        client.get("/health")

    assert provider.call_count == 0


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def test_ready_returns_200_when_provider_is_configured():
    with patch("app.main.settings") as settings:
        settings.is_configured = True

        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_with_error_envelope_when_unconfigured():
    """A 503 must use the same envelope as every other failure, so the NestJS
    client's status-to-code mapping resolves it to `provider_unavailable`."""
    with patch("app.main.settings") as settings:
        settings.is_configured = False

        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_ready_message_does_not_reveal_configuration_secrets():
    with patch("app.main.settings") as settings:
        settings.is_configured = False

        response = client.get("/ready")

    assert "sk-" not in response.text
    assert "PROVIDER_API_KEY value" not in response.text


def test_ready_makes_no_llm_call():
    """Readiness is a configuration check, never a model round-trip.

    This is the property that keeps NestJS's ``/ready`` fast: it must never
    inherit the multi-second (here, multi-minute) LLM latency.
    """
    provider = RecordingProvider("unused")

    with patch("app.main._build_provider", return_value=provider):
        with patch("app.main.settings") as settings:
            settings.is_configured = True
            response = client.get("/ready")

    assert response.status_code == 200
    assert provider.call_count == 0


def test_ready_responds_within_a_fast_budget():
    """Guards against a future change that sneaks a network call into /ready."""
    import time

    start = time.perf_counter()
    with patch("app.main.settings") as settings:
        settings.is_configured = True
        response = client.get("/ready")
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 1.0, f"/ready took {elapsed:.3f}s — a network call may have leaked in"


# ---------------------------------------------------------------------------
# Both endpoints together
# ---------------------------------------------------------------------------


def test_health_and_ready_agree_when_configured():
    """NestJS derives `aiEngine=ok` from this combination; they must not disagree."""
    with patch("app.main.settings") as settings:
        settings.is_configured = True

        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == ready.status_code == 200


def test_health_stays_200_while_ready_reports_503():
    """Unconfigured engine is alive but not ready — the standard distinction."""
    with patch("app.main.settings") as settings:
        settings.is_configured = False

        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code == 503
