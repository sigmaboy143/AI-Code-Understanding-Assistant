"""Startup and import cost.

Category
--------
**Performance.** Import and ASGI-startup cost, measured the only way it can be
measured honestly: in a **fresh subprocess**, because by the time a test runs,
``app.main`` is already imported and the cold-start cost is long gone.

Method
------
``python -X importtime`` is a CPython built-in, so no extra dependency is
needed.  Its stderr carries one line per imported module, which gives a real
per-module breakdown rather than a single opaque number.  The wall clock is
measured separately with :func:`time.perf_counter` around the subprocess.

Why this is in the performance suite
------------------------------------
``app.main`` builds the whole FastAPI application at import time, so a change
that adds an eager import to that path lengthens every start-up — container
restarts, scale-from-zero, and every CI job — even though it costs a single
request nothing.  That class of regression is invisible to the request-path
measurements in the other modules.

Bounds
------
The ceiling is deliberately loose.  Interpreter start-up dominates, it varies a
lot between machines, and the claim under test is "the AI Engine still starts
promptly", not "it starts within N milliseconds".
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

import app
from tests.performance.harness import (
    STARTUP_CEILING_S,
    record,
    summarise,
)

#: Root of the AI Engine package, i.e. the directory that must be importable as
#: ``app``.  The suite is often run from the repository root, where ``app`` is
#: not on ``sys.path``, so the subprocess is given this directory explicitly
#: rather than inheriting whatever the parent process happened to have.
ENGINE_ROOT = Path(app.__file__).resolve().parent.parent

#: How many fresh interpreters to launch.  Three is enough for a median that is
#: stable, and keeps the module under a couple of seconds.
STARTUP_SAMPLE_COUNT = 3

#: Substrings whose cumulative import time is interesting for this engine.
WATCHED_MODULES = ("fastapi", "pydantic", "httpx", "starlette", "app.main")

_IMPORT_LINE = re.compile(
    r"^import time:\s+(?P<self_us>\d+)\s*\|\s+(?P<cumulative_us>\d+)\s*\|\s+(?P<name>.+)$"
)


def _child_env() -> dict[str, str]:
    """Return an environment in which ``import app`` resolves to this engine."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{ENGINE_ROOT}{os.pathsep}{existing}" if existing else str(ENGINE_ROOT)
    )
    return env


def _run(script: str, *extra_flags: str) -> tuple[float, subprocess.CompletedProcess]:
    """Run *script* in a fresh interpreter and return (wall seconds, result)."""
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, *extra_flags, "-c", script],
        capture_output=True,
        text=True,
        timeout=STARTUP_CEILING_S * 3,
        cwd=str(ENGINE_ROOT),
        env=_child_env(),
    )
    return time.perf_counter() - start, result


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def test_importing_the_ai_engine_is_prompt():
    """``from app.main import app`` — the check every CI job already performs.

    Measured in a fresh interpreter, because an in-process measurement would
    measure the import cache, not the import.
    """
    script = "from app.main import app; assert app is not None"
    samples: list[float] = []
    result = None

    for _ in range(STARTUP_SAMPLE_COUNT):
        elapsed, result = _run(script)
        samples.append(elapsed)

    assert result is not None and result.returncode == 0, (
        f"importing the AI Engine failed: {result.stderr if result else ''}"
    )

    measurement = record(
        summarise(
            f"cold start: python -c 'from app.main import app' (n={STARTUP_SAMPLE_COUNT})",
            [value * 1000.0 for value in samples],
            notes="includes CPython interpreter start-up and site initialisation",
        )
    )
    print(f"[perf] cold start median {measurement.median_ms:.1f}ms")

    assert measurement.max_ms < STARTUP_CEILING_S * 1000.0, (
        f"cold start took {measurement.max_ms:.1f}ms, over the "
        f"{STARTUP_CEILING_S}s ceiling: {measurement.summary()}"
    )


def test_building_the_asgi_app_through_a_test_client_is_prompt():
    """Instantiating the app builds the real router and exception handlers.

    This is the part of start-up that a ``-c "import app"`` check does not
    cover, and it is what a container actually pays before serving traffic.
    """
    script = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        "seen = []\n"
        "for path in ('/health', '/ready'):\n"
        "    response = client.get(path)\n"
        "    assert response.status_code in (200, 503), (path, response.status_code)\n"
        "    seen.append(f'{path}={response.status_code}')\n"
        # Printed so the parent can confirm the probes really answered rather
        # than merely that the process exited zero.
        "print(' '.join(seen), flush=True)\n"
    )
    samples: list[float] = []
    statuses: list[str] = []
    result = None

    for _ in range(STARTUP_SAMPLE_COUNT):
        elapsed, result = _run(script)
        samples.append(elapsed)
        if result.returncode == 0 and result.stdout.strip():
            statuses.append(result.stdout.strip().splitlines()[-1])

    assert result is not None and result.returncode == 0, (
        f"the ASGI app did not start: {result.stderr if result else ''}"
    )

    measurement = record(
        summarise(
            f"startup + TestClient probes /health and /ready (n={STARTUP_SAMPLE_COUNT})",
            [value * 1000.0 for value in samples],
            notes="no port is bound; the router and handlers are built for real",
        )
    )
    print(f"[perf] startup-with-probes median {measurement.median_ms:.1f}ms")

    assert measurement.max_ms < STARTUP_CEILING_S * 1000.0, measurement.summary()
    assert statuses == ["/health=200 /ready=200"] * STARTUP_SAMPLE_COUNT, (
        f"the startup probe did not answer on both endpoints every run: {statuses}"
    )


def test_import_time_breakdown_is_available_for_review():
    """Record the per-module import cost so start-up regressions are attributable.

    ``-X importtime`` writes one line per module to stderr.  A regression that
    lengthens start-up is only actionable once you know *which* import caused
    it, so the watched modules are extracted and reported rather than merely
    asserting that the total is small.
    """
    _, result = _run("from app.main import app", "-X", "importtime")
    assert result.returncode == 0, result.stderr

    breakdown: dict[str, float] = {}
    self_time: dict[str, float] = {}
    for line in result.stderr.splitlines():
        match = _IMPORT_LINE.match(line.strip())
        if not match:
            continue
        name = match.group("name").strip()
        cumulative_us = int(match.group("cumulative_us"))
        if any(watched in name for watched in WATCHED_MODULES):
            # Keep the deepest match for a name, so a nested module is not
            # overwritten by an unrelated later line mentioning the same word.
            previous = breakdown.get(name)
            if previous is None or cumulative_us > previous:
                breakdown[name] = cumulative_us
                self_time[name] = int(match.group("self_us"))

    assert breakdown, (
        "no importtime records were parsed; the -X importtime output format "
        "appears to have changed, so the breakdown is no longer trustworthy"
    )

    print("[perf] top cumulative import costs:")
    for name, value in sorted(breakdown.items(), key=lambda kv: -kv[1])[:8]:
        print(
            f"[perf]   {name}: {value / 1000.0:.1f}ms cumulative, "
            f"{self_time[name] / 1000.0:.1f}ms self"
        )

    # ``app.main`` is cumulative, so it *contains* the cost of fastapi and
    # pydantic.  What the engine's own code adds on top of its dependencies is
    # the sum of the self times of the ``app`` package, which is the number that
    # would grow if someone added an eager import to this project.
    engine_self_us = sum(
        self_us for name, self_us in self_time.items() if name == "app" or name.startswith("app.")
    )
    print(
        f"[perf] engine's own import self-time: {engine_self_us / 1000.0:.1f}ms "
        f"across {sum(1 for n in self_time if n == 'app' or n.startswith('app.'))} modules"
    )

    assert engine_self_us > 0, (
        "no modules from the `app` package appeared in the breakdown, so the "
        "engine's own import cost is unknown"
    )
    assert max(breakdown.values()) < STARTUP_CEILING_S * 1_000_000, (
        f"a single import took {max(breakdown.values()) / 1000.0:.0f}ms, which "
        f"would dominate start-up"
    )


def test_startup_does_not_require_a_live_provider():
    """Start-up must not depend on Ollama, weights, or any credential.

    If it did, a cold container would fail before it could serve ``/ready``,
    and the orchestration the deployment relies on would not start.
    """
    script = (
        "import os\n"
        # Point the provider at an unroutable address and name a model that is
        # certainly not present, exactly as CI does.
        "os.environ['PROVIDER'] = 'ollama'\n"
        "os.environ['MODEL'] = 'qwen3:8b'\n"
        "os.environ['PROVIDER_BASE_URL'] = 'http://192.0.2.1:11434'\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        "assert client.get('/health').status_code == 200\n"
    )
    _, result = _run(script)

    assert result.returncode == 0, (
        f"start-up needed something it should not have: {result.stderr}"
    )


@pytest.mark.parametrize("endpoint", ["/health", "/ready"])
def test_startup_endpoints_answer_before_any_provider_is_built(endpoint):
    """Both liveness endpoints must answer while the provider is unreachable.

    Ties the start-up measurement to the behaviour it exists to protect: a
    probe that had to reach the model to answer would be useless as a liveness
    signal.
    """
    script = (
        "import os\n"
        "os.environ['PROVIDER'] = 'ollama'\n"
        "os.environ['PROVIDER_BASE_URL'] = 'http://192.0.2.1:11434'\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        f"response = client.get('{endpoint}')\n"
        "assert response.status_code in (200, 503), response.status_code\n"
    )
    _, result = _run(script)

    assert result.returncode == 0, result.stderr
