"""Deterministic performance testing for the AI Engine.

Category
--------
**Performance.** This package measures how long the engine's own work takes, so
that a future change that quietly makes the request path an order of magnitude
more expensive is caught by ``pytest`` rather than by a user.

What is measured here
---------------------
1. ``test_provider_performance``  — the cost of one provider round trip through
   a **real** ``OllamaProvider`` and a **real** ``httpx`` client, with only the
   socket replaced.  This is engine-side overhead: it deliberately *excludes*
   model inference time.
2. ``test_request_performance``  — the cost of one full in-process
   ``POST /api/v1/code-understanding``, and a stage-by-stage decomposition of
   where that time goes.
3. ``test_timeout_performance``   — real timeout enforcement against a real
   loopback socket, and the real ``ProviderError`` → 504 mapping that the Phase
   13 blocker depends on.

What is deliberately *not* measured here
---------------------------------------
- **Model response duration.**  A real number for this needs ``qwen3:8b`` to
  answer, and the live full-analysis request does not complete inside the read
  timeout (Phase 13).  The performance suite therefore reports this as **NOT
  MEASURABLE** rather than substituting a number it cannot stand behind.  A
  bounded, out-of-band live probe is recorded in
  ``docs/ai-performance-report.md`` instead.
- **NestJS → AI Engine end-to-end latency.**  ``apps/api`` is not part of this
  branch, so there is no caller to measure against.
- **Throughput / concurrency under real load.**  One model on one local daemon
  gives no meaningful capacity number, and load-testing it would only reproduce
  the Phase 13 timeout more slowly.

Determinism and safety
----------------------
Every measurement here is driven by synthetic fixtures — the two-line
``def add(a, b): return a + b`` snippet and a hand-written upstream body.  No
repository source, no credentials, and nothing confidential is used.  The only
socket that is opened is a loopback (``127.0.0.1``) listener created and torn
down by the test itself; no external network and no Ollama daemon is required.

Thresholds
----------
Performance assertions are ceilings with wide headroom, and the load-bearing
assertions are **structural** (retry counts, stage accounting, timeout bounds)
rather than absolute microseconds.  A slow or shared CI runner must not produce
a red build; a genuine order-of-magnitude regression still must.

Production timeout values are never modified.  Where a short budget is needed to
keep a test fast, the budget belongs to a provider instance created *inside the
test*, never to ``app.config`` or to the default in ``OllamaProvider``.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from math import ceil

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Samples for the cheap, high-count micro-measurements.  Chosen so a full run
#: of this package stays a few seconds: 300 x ~1 ms is 0.3 s of real work.
SAMPLE_COUNT = 300

#: Untimed calls run before every measurement, so the reported numbers describe
#: steady-state behaviour rather than first-call costs such as lazy imports and
#: allocator warm-up.  Tests that also count calls need this value.
WARMUP_ITERATIONS = 3

#: Samples for the end-to-end HTTP measurement.  Lower than ``SAMPLE_COUNT``
#: because each sample crosses the whole ASGI stack plus a JSON round trip.
#: The medians here are already stable well below this count.
REQUEST_SAMPLE_COUNT = 120

#: Samples per stage in the decomposition.  Each one is a full in-process
#: analysis, so this is kept modest to bound the suite's runtime.
STAGE_SAMPLE_COUNT = 60

#: Samples for the relative comparisons (health vs analysis, dependency vs
#: explanation, 200 vs 502 vs 504).  These assert ratios, not absolute values,
#: so they need fewer samples than the headline numbers.
COMPARISON_SAMPLE_COUNT = 80

#: Artificial provider latency used to check that concurrent requests overlap.
#: Long enough to dominate scheduling noise, short enough to keep the suite fast.
PROVIDER_DELAY_MS = 20

#: Samples for the real-socket timeout measurement.  Each sample costs a full
#: ``TIMEOUT_PROBE_BUDGET_S`` of wall clock, so this stays deliberately small.
TIMEOUT_SAMPLE_COUNT = 3

#: Budget, in seconds, for the loopback timeout probe.  Chosen to be long enough
#: that a healthy request is never mistaken for a timeout, and short enough that
#: three samples cost about three seconds.
TIMEOUT_PROBE_BUDGET_S = 1.0

#: Synthetic upstream delay, in milliseconds, used to show that engine overhead
#: is *additive* against provider latency rather than multiplying it.
SIMULATED_UPSTREAM_LATENCY_MS = 50

#: Ceiling for a single ``OllamaProvider.complete`` call with the socket stubbed.
#: Measured in the low single-digit milliseconds; the headroom is deliberate.
PROVIDER_CALL_CEILING_MS = 250.0

#: Ceiling for one full in-process ``POST /api/v1/code-understanding``.  Roughly
#: two orders of magnitude above the measured value.
AI_REQUEST_CEILING_MS = 750.0

#: Ceiling for the AI Engine's import + ASGI-app construction, measured in a
#: fresh subprocess.  Includes interpreter start-up, so it is deliberately loose.
STARTUP_CEILING_S = 20.0

#: How far a real timeout may overshoot its budget before the measurement is
#: treated as a failure rather than as scheduler noise.  Generous, because the
#: check is looking for "did it fire at all, and roughly on time".
TIMEOUT_OVERSHOOT_TOLERANCE = 3.0

#: How far a real timeout may fire *early*.  It must not: a premature timeout
#: would fail healthy requests in production.
TIMEOUT_EARLY_TOLERANCE_S = 0.25

#: How far the sum of the per-stage medians may differ from the whole-call
#: median before the decomposition is considered to have missed real work.  The
#: check is two-sided: this catches work appearing *outside* the instrumented
#: stages, and a stage being double-counted, without being defeated by the
#: scheduler noise that a shared CI runner produces.
STAGE_ACCOUNTING_TOLERANCE = 0.5


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    """An immutable timing summary for one measured operation.

    Every field is an *actual* observed value.  Nothing here is a target, an
    estimate, or a value copied from another machine.
    """

    name: str
    count: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    stdev_ms: float
    notes: str = ""

    def summary(self) -> str:
        """Return a one-line, human-readable description of the measurement."""
        return (
            f"{self.name}: n={self.count} "
            f"min={self.min_ms:.3f}ms "
            f"median={self.median_ms:.3f}ms "
            f"mean={self.mean_ms:.3f}ms "
            f"p95={self.p95_ms:.3f}ms "
            f"max={self.max_ms:.3f}ms "
            f"stdev={self.stdev_ms:.3f}ms"
        )

    def as_dict(self) -> dict:
        """Return the measurement as plain data, for reporting."""
        return {
            "name": self.name,
            "count": self.count,
            "min_ms": round(self.min_ms, 3),
            "median_ms": round(self.median_ms, 3),
            "mean_ms": round(self.mean_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "stdev_ms": round(self.stdev_ms, 3),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return the nearest-rank percentile of *values*.

    Nearest-rank is used rather than an interpolating estimator because every
    value here is a real observation: the returned number is always one of the
    samples that actually happened, which is what a performance report should
    be quoting.
    """
    if not values:
        raise ValueError("percentile() needs at least one sample")
    ordered = sorted(values)
    rank = max(1, ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarise(name: str, durations_ms: Sequence[float], notes: str = "") -> Measurement:
    """Reduce per-iteration millisecond samples to a :class:`Measurement`."""
    if not durations_ms:
        raise ValueError(f"no samples were collected for {name!r}")
    return Measurement(
        name=name,
        count=len(durations_ms),
        min_ms=min(durations_ms),
        max_ms=max(durations_ms),
        mean_ms=statistics.fmean(durations_ms),
        median_ms=statistics.median(durations_ms),
        p95_ms=percentile(durations_ms, 0.95),
        stdev_ms=statistics.stdev(durations_ms) if len(durations_ms) > 1 else 0.0,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Timers
# ---------------------------------------------------------------------------


def measure(
    name: str,
    iterations: int,
    operation: Callable[[], object],
    *,
    warmup: int = WARMUP_ITERATIONS,
    notes: str = "",
) -> Measurement:
    """Time a synchronous *operation* and return the summary.

    *warmup* iterations run first and are discarded, so the reported numbers
    describe steady-state behaviour rather than first-call costs such as lazy
    imports and allocator warm-up.
    """
    for _ in range(warmup):
        operation()

    durations: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        durations.append((time.perf_counter() - start) * 1000.0)
    return summarise(name, durations, notes=notes)


async def measure_async(
    name: str,
    iterations: int,
    operation: Callable[[], Awaitable[object]],
    *,
    warmup: int = WARMUP_ITERATIONS,
    notes: str = "",
) -> Measurement:
    """Time an awaitable *operation* and return the summary.

    Uses :func:`time.perf_counter`, the highest-resolution monotonic clock
    available, so the values are durations and not wall-clock timestamps.
    """
    for _ in range(warmup):
        await operation()

    durations: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        await operation()
        durations.append((time.perf_counter() - start) * 1000.0)
    return summarise(name, durations, notes=notes)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_RECORDED: list[Measurement] = []


def record(measurement: Measurement) -> Measurement:
    """Record *measurement* for the end-of-session table and return it.

    The table is printed to stdout.  Run the suite with ``-s`` to see it, e.g.::

        python -m pytest apps/ai-engine/tests/performance -q -s
    """
    _RECORDED.append(measurement)
    print(f"[perf] {measurement.summary()}")
    if measurement.notes:
        print(f"[perf]   note: {measurement.notes}")
    return measurement


def recorded() -> tuple[Measurement, ...]:
    """Return every measurement recorded so far, in order."""
    return tuple(_RECORDED)


def print_table() -> None:
    """Print the accumulated measurements as an aligned table."""
    if not _RECORDED:
        return
    header = f"{'measurement':<46} {'n':>5} {'min':>9} {'median':>9} {'mean':>9} {'p95':>9} {'max':>9}"
    print("\n=== AI performance measurements ===")
    print(header)
    print("-" * len(header))
    for item in _RECORDED:
        print(
            f"{item.name:<46} {item.count:>5} "
            f"{item.min_ms:>8.3f}ms {item.median_ms:>8.3f}ms "
            f"{item.mean_ms:>8.3f}ms {item.p95_ms:>8.3f}ms {item.max_ms:>8.3f}ms"
        )
    print("=" * len(header) + "\n")
