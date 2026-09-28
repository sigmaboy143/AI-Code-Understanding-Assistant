/**
 * Phase 6 Step 3 tests for request correlation.
 *
 * The concurrency cases matter most here. Correlation bugs are invisible in a
 * test that awaits each request to completion, because a sequential test cannot
 * observe leakage. The interleaved cases below deliberately hold one request
 * open while a second one runs, which is the only way to prove the
 * AsyncLocalStorage contexts are genuinely separate.
 */
import {
  getCorrelationId,
  runWithCorrelation,
} from './request-correlation.js';

/** Yields to the microtask queue so overlapping work can interleave. */
function tick(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

describe('getCorrelationId outside a context', () => {
  it('returns undefined when no correlation context is bound', () => {
    expect(getCorrelationId()).toBeUndefined();
  });
});

describe('runWithCorrelation', () => {
  it('makes the ID available synchronously inside the callback', () => {
    runWithCorrelation('req-sync', () => {
      expect(getCorrelationId()).toBe('req-sync');
    });
  });

  it('returns the callback return value unchanged', () => {
    expect(runWithCorrelation('req-sync', () => 42)).toBe(42);
  });

  it('returns a promise unchanged for an async callback', async () => {
    const result = await runWithCorrelation('req-async', async () => 'done');

    expect(result).toBe('done');
  });

  it('retains the ID across nested async execution', async () => {
    const observed = await runWithCorrelation('req-nested', async () => {
      await tick();
      const afterTick = getCorrelationId();
      await tick();
      await tick();

      return { afterTick, afterMoreTicks: getCorrelationId() };
    });

    expect(observed).toEqual({
      afterTick: 'req-nested',
      afterMoreTicks: 'req-nested',
    });
  });

  it('retains the ID inside a nested runWithCorrelation of the same value', async () => {
    const observed = await runWithCorrelation('req-outer', async () =>
      runWithCorrelation('req-outer', async () => {
        await tick();
        return getCorrelationId();
      }),
    );

    expect(observed).toBe('req-outer');
  });

  it('restores undefined after the callback completes', () => {
    runWithCorrelation('req-scoped', () => undefined);

    expect(getCorrelationId()).toBeUndefined();
  });

  it('restores undefined after an async callback completes', async () => {
    await runWithCorrelation('req-scoped', async () => {
      await tick();
    });

    expect(getCorrelationId()).toBeUndefined();
  });
});

describe('runWithCorrelation isolation', () => {
  it('keeps two sequential contexts distinct', () => {
    runWithCorrelation('req-first', () => {
      expect(getCorrelationId()).toBe('req-first');
    });
    runWithCorrelation('req-second', () => {
      expect(getCorrelationId()).toBe('req-second');
    });

    expect(getCorrelationId()).toBeUndefined();
  });

  it('does not leak an inner ID out to the outer context', () => {
    runWithCorrelation('req-outer', () => {
      runWithCorrelation('req-inner', () => {
        expect(getCorrelationId()).toBe('req-inner');
      });

      expect(getCorrelationId()).toBe('req-outer');
    });
  });

  it('does not leak between two concurrent contexts', async () => {
    const observations: Record<string, string | undefined> = {};

    // Both requests are started before either is awaited, and each yields
    // several times, so their continuations interleave on the event loop.
    const first = runWithCorrelation('req-concurrent-a', async () => {
      await tick();
      observations.firstEarly = getCorrelationId();
      await tick();
      await tick();
      observations.firstLate = getCorrelationId();
      return getCorrelationId();
    });

    const second = runWithCorrelation('req-concurrent-b', async () => {
      await tick();
      observations.secondEarly = getCorrelationId();
      await tick();
      await tick();
      observations.secondLate = getCorrelationId();
      return getCorrelationId();
    });

    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(firstResult).toBe('req-concurrent-a');
    expect(secondResult).toBe('req-concurrent-b');
    expect(observations).toEqual({
      firstEarly: 'req-concurrent-a',
      firstLate: 'req-concurrent-a',
      secondEarly: 'req-concurrent-b',
      secondLate: 'req-concurrent-b',
    });
  });

  it('isolates many concurrent contexts', async () => {
    const ids = Array.from({ length: 25 }, (_, index) => `req-parallel-${index}`);

    const results = await Promise.all(
      ids.map((id) =>
        runWithCorrelation(id, async () => {
          await tick();
          const midFlight = getCorrelationId();
          await tick();
          return { id, midFlight, final: getCorrelationId() };
        }),
      ),
    );

    for (const result of results) {
      expect(result.midFlight).toBe(result.id);
      expect(result.final).toBe(result.id);
    }
  });
});
