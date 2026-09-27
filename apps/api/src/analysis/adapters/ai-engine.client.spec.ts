import { jest } from '@jest/globals';

import { AiEngineClient, AiEngineClientError } from './ai-engine.client.js';
import { AppLogger } from '../../common/logging/app-logger.js';
import type { LogEntry } from '../../common/logging/log-sink.js';
import type { LogSink } from '../../common/logging/log-sink.js';
import { runWithCorrelation } from '../../common/correlation/request-correlation.js';
import type { AiEngineConfig } from '../config/ai-engine.config.js';
import type { AiEngineRequestContract } from '../contracts/ai-engine-request.contract.js';
import type { AiEngineResponseContract } from '../contracts/ai-engine-response.contract.js';

// ---------------------------------------------------------------------------
// Helpers

const TEST_CONFIG: AiEngineConfig = {
  baseUrl: 'http://test-ai-engine',
  timeoutMs: 5_000,
};

const MINIMAL_REQUEST: AiEngineRequestContract = {
  source_code: 'console.log("hello")',
  language: 'typescript',
  file_path: null,
  question: null,
  context: null,
  analyses: [],
};

const MINIMAL_RESPONSE: AiEngineResponseContract = {
  summary: 'A simple log statement.',
  metadata: { language: 'typescript', file_path: null, analyses: [] },
  confidence: { level: 'LOW', evidence: [], notes: '' },
  explanation: null,
  structure: null,
  dependencies: null,
  improvements: null,
};

/**
 * Captured log entries for the current test.
 *
 * A fake LOG_SINK is used rather than a console or Logger spy so the assertions
 * read the exact structured entry the client emitted, with no dependence on how
 * a backend would render it.
 */
const capturedEntries: LogEntry[] = [];

const fakeSink: LogSink = {
  log: (entry: LogEntry) => {
    capturedEntries.push(entry);
  },
};

function makeClient(): AiEngineClient {
  // Construct without NestJS DI — inject config value directly.
  // Phase 6: the client also takes an AppLogger, so a capturing fake sink is
  // supplied here. This is the only change to the shared factory; the original
  // Phase 3 and Phase 5 test bodies below are unmodified.
  capturedEntries.length = 0;
  // AppLogger takes only a sink; the 'AiEngineClient' tag is applied by the
  // client itself via withContext(), so it is not passed here.
  return new AiEngineClient(TEST_CONFIG, new AppLogger(fakeSink));
}

function mockFetchOk(body: unknown): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(body),
  } as unknown as Response);
}

function mockFetchError(status: number, errorBody: unknown): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve(errorBody),
  } as unknown as Response);
}

function mockFetchThrow(err: unknown): void {
  global.fetch = jest.fn().mockRejectedValue(err);
}

/** Asserts the promise rejects with AiEngineClientError carrying the given code. */
async function expectClientError(
  promise: Promise<unknown>,
  expectedCode: string,
): Promise<void> {
  try {
    await promise;
    throw new Error('Expected promise to reject but it resolved');
  } catch (err: unknown) {
    expect(err).toBeInstanceOf(AiEngineClientError);
    expect((err as AiEngineClientError).code).toBe(expectedCode);
  }
}

// ---------------------------------------------------------------------------

describe('AiEngineClient', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  // 1. Correct endpoint URL
  it('sends POST to {baseUrl}/api/v1/code-understanding', async () => {
    mockFetchOk(MINIMAL_RESPONSE);
    await makeClient().post(MINIMAL_REQUEST);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://test-ai-engine/api/v1/code-understanding',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  // 2. POST method
  it('uses POST method', async () => {
    mockFetchOk(MINIMAL_RESPONSE);
    await makeClient().post(MINIMAL_REQUEST);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  // 3. Content-Type header
  it('sets Content-Type: application/json', async () => {
    mockFetchOk(MINIMAL_RESPONSE);
    await makeClient().post(MINIMAL_REQUEST);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });

  // 4. JSON body serialisation
  it('serialises request body as JSON', async () => {
    mockFetchOk(MINIMAL_RESPONSE);
    await makeClient().post(MINIMAL_REQUEST);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ body: JSON.stringify(MINIMAL_REQUEST) }),
    );
  });

  // 5. Successful 200 response
  it('returns parsed response on HTTP 200', async () => {
    mockFetchOk(MINIMAL_RESPONSE);
    const result = await makeClient().post(MINIMAL_REQUEST);
    expect(result).toEqual(MINIMAL_RESPONSE);
  });

  // 6. 422 → validation_error
  it('throws AiEngineClientError("validation_error") on HTTP 422', async () => {
    mockFetchError(422, { error: { code: 'VALIDATION_ERROR', message: 'bad input' } });
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'validation_error');
  });

  // 7. 503 → provider_unavailable
  it('throws AiEngineClientError("provider_unavailable") on HTTP 503', async () => {
    mockFetchError(503, { error: { code: 'PROVIDER_UNAVAILABLE', message: 'down' } });
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'provider_unavailable');
  });

  // 8. 504 → provider_timeout
  it('throws AiEngineClientError("provider_timeout") on HTTP 504', async () => {
    mockFetchError(504, { error: { code: 'PROVIDER_TIMEOUT', message: 'timed out' } });
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'provider_timeout');
  });

  // 9. 502 → provider_error
  it('throws AiEngineClientError("provider_error") on HTTP 502', async () => {
    mockFetchError(502, { error: { code: 'PROVIDER_ERROR', message: 'bad gateway' } });
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'provider_error');
  });

  // 10. 500 → internal_error
  it('throws AiEngineClientError("internal_error") on HTTP 500', async () => {
    mockFetchError(500, { error: { code: 'INTERNAL_ERROR', message: 'server error' } });
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'internal_error');
  });

  // 11. Network failure
  it('throws AiEngineClientError("network_error") when fetch rejects', async () => {
    mockFetchThrow(new TypeError('Failed to fetch'));
    await expectClientError(makeClient().post(MINIMAL_REQUEST), 'network_error');
  });

  // 12. Timeout via AbortController
  it('throws AiEngineClientError("timeout") when AbortController fires', async () => {
    jest.useFakeTimers();

    const abortError = new DOMException('The operation was aborted.', 'AbortError');
    global.fetch = jest.fn().mockImplementation(
      (_url: unknown, options: { signal?: AbortSignal }) =>
        new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(abortError));
        }),
    );

    const client = makeClient();
    const postPromise = client.post(MINIMAL_REQUEST);
    jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

    await expectClientError(postPromise, 'timeout');
  });

  // 13. Upstream message captured from error envelope
  it('captures upstream message from error envelope', async () => {
    mockFetchError(422, {
      error: { code: 'VALIDATION_ERROR', message: 'source_code is required' },
    });
    try {
      await makeClient().post(MINIMAL_REQUEST);
      throw new Error('Expected rejection');
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(AiEngineClientError);
      expect((err as AiEngineClientError).upstreamMessage).toBe('source_code is required');
    }
  });
});

// ---------------------------------------------------------------------------
// Phase 5 — readiness probe (additive; post() above is untouched)
// ---------------------------------------------------------------------------

const READINESS_URL = 'http://test-ai-engine/ready';

/** Responds ok with a json() spy, so body parsing can be detected. */
function mockFetchReady(status: number): () => unknown {
  const json = jest.fn(() => Promise.resolve({ status: 'ready' }));
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json,
  } as unknown as Response);
  return json;
}

describe('AiEngineClient.checkReadiness', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  // 1. Successful 2xx
  it('resolves on HTTP 200', async () => {
    mockFetchReady(200);
    await expect(makeClient().checkReadiness()).resolves.toBeUndefined();
  });

  it('resolves on HTTP 204 (2xx with no body)', async () => {
    mockFetchReady(204);
    await expect(makeClient().checkReadiness()).resolves.toBeUndefined();
  });

  // 2. Method
  it('uses GET method', async () => {
    mockFetchReady(200);
    await makeClient().checkReadiness();
    expect(global.fetch).toHaveBeenCalledWith(
      READINESS_URL,
      expect.objectContaining({ method: 'GET' }),
    );
  });

  // 3. Target URL
  it('targets {baseUrl}/ready', async () => {
    mockFetchReady(200);
    await makeClient().checkReadiness();
    expect(global.fetch).toHaveBeenCalledWith(
      READINESS_URL,
      expect.any(Object),
    );
  });

  // 4. No request body
  it('sends no request body', async () => {
    mockFetchReady(200);
    await makeClient().checkReadiness();
    expect(global.fetch).toHaveBeenCalledWith(
      READINESS_URL,
      expect.not.objectContaining({ body: expect.anything() }),
    );
  });

  // 5. No unnecessary Content-Type
  it('sends no Content-Type header', async () => {
    mockFetchReady(200);
    await makeClient().checkReadiness();
    expect(global.fetch).toHaveBeenCalledWith(
      READINESS_URL,
      expect.not.objectContaining({ headers: expect.anything() }),
    );
  });

  // 6–9. Non-2xx status mapping reuses the existing STATUS_TO_CODE table
  it('maps HTTP 503 to provider_unavailable', async () => {
    mockFetchReady(503);
    await expectClientError(makeClient().checkReadiness(), 'provider_unavailable');
  });

  it('maps HTTP 504 to provider_timeout', async () => {
    mockFetchReady(504);
    await expectClientError(makeClient().checkReadiness(), 'provider_timeout');
  });

  it('maps HTTP 502 to provider_error', async () => {
    mockFetchReady(502);
    await expectClientError(makeClient().checkReadiness(), 'provider_error');
  });

  it('maps HTTP 500 to internal_error', async () => {
    mockFetchReady(500);
    await expectClientError(makeClient().checkReadiness(), 'internal_error');
  });

  it('maps an unmapped status (418) to internal_error', async () => {
    mockFetchReady(418);
    await expectClientError(makeClient().checkReadiness(), 'internal_error');
  });

  // 10. Network failure
  it('maps a rejected fetch to network_error', async () => {
    mockFetchThrow(new TypeError('Failed to fetch'));
    await expectClientError(makeClient().checkReadiness(), 'network_error');
  });

  // 11. AbortError → timeout
  it('maps AbortError to timeout', async () => {
    jest.useFakeTimers();

    const abortError = new DOMException('The operation was aborted.', 'AbortError');
    global.fetch = jest.fn().mockImplementation(
      (_url: unknown, options: { signal?: AbortSignal }) =>
        new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(abortError));
        }),
    );

    const promise = makeClient().checkReadiness();
    jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

    await expectClientError(promise, 'timeout');
  });

  // 12. Timer cleanup
  it('clears the timeout timer on success', async () => {
    jest.useFakeTimers();
    mockFetchReady(200);

    await makeClient().checkReadiness();

    expect(jest.getTimerCount()).toBe(0);
  });

  it('clears the timeout timer on failure', async () => {
    jest.useFakeTimers();
    mockFetchThrow(new TypeError('Failed to fetch'));

    await expectClientError(makeClient().checkReadiness(), 'network_error');

    expect(jest.getTimerCount()).toBe(0);
  });

  it('clears the timeout timer on a non-2xx response', async () => {
    jest.useFakeTimers();
    mockFetchReady(503);

    await expectClientError(makeClient().checkReadiness(), 'provider_unavailable');

    expect(jest.getTimerCount()).toBe(0);
  });

  // 13. Body is never parsed
  it('never parses the response body on success', async () => {
    const json = mockFetchReady(200);

    await makeClient().checkReadiness();

    expect(json).not.toHaveBeenCalled();
  });

  it('never parses the response body on failure and captures no upstream message', async () => {
    const json = mockFetchReady(503);

    try {
      await makeClient().checkReadiness();
      throw new Error('Expected rejection');
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(AiEngineClientError);
      // No upstream text is retained, so nothing can leak through the client.
      expect((err as AiEngineClientError).upstreamMessage).toBeUndefined();
    }
    expect(json).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Phase 6 â€” observability (additive; the Phase 3 and Phase 5 blocks above are
// unmodified)
//
// The invariant under test: ONE AI ENGINE INTERACTION = ONE LOG ENTRY.
// Every case below asserts on the *count* of entries as well as their content,
// because a duplicated entry and a missing entry are equally damaging and only
// a count assertion catches the duplicate.
// ---------------------------------------------------------------------------

/** Responds ok with an explicit status, so the logged status is observable. */
function mockFetchOkWithStatus(status: number, body: unknown): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response);
}

/** Rejects only once the AbortController has fired, as the timeout path does. */
function mockFetchAborting(): void {
  const abortError = new DOMException('The operation was aborted.', 'AbortError');
  global.fetch = jest.fn().mockImplementation(
    (_url: unknown, options: { signal?: AbortSignal }) =>
      new Promise<Response>((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(abortError));
      }),
  );
}

describe('AiEngineClient observability', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // Exactly one entry per invocation

  describe('one log entry per interaction', () => {
    it('emits exactly one entry on a successful analysis', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry on a 4xx analysis response', async () => {
      mockFetchError(422, { error: { message: 'bad input' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'validation_error',
      );

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry on a 5xx analysis response', async () => {
      mockFetchError(503, { error: { message: 'down' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'provider_unavailable',
      );

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry on a network failure', async () => {
      mockFetchThrow(new TypeError('Failed to fetch'));

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry on a timeout', async () => {
      jest.useFakeTimers();
      mockFetchAborting();

      const client = makeClient();
      const promise = client.post(MINIMAL_REQUEST);
      jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

      await expectClientError(promise, 'timeout');
      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry per readiness probe on success', async () => {
      mockFetchReady(200);

      await makeClient().checkReadiness();

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits exactly one entry per readiness probe on failure', async () => {
      mockFetchReady(503);

      await expectClientError(
        makeClient().checkReadiness(),
        'provider_unavailable',
      );

      expect(capturedEntries).toHaveLength(1);
    });

    it('emits one entry per invocation across three sequential calls', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);
      const client = makeClient();

      await client.post(MINIMAL_REQUEST);
      await client.post(MINIMAL_REQUEST);
      await client.checkReadiness();

      expect(capturedEntries).toHaveLength(3);
    });

    it('does not accumulate entries between tests', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);
      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries).toHaveLength(1);
    });
  });

  // -----------------------------------------------------------------------
  // Levels

  describe('log levels', () => {
    it('logs a successful analysis at info', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].level).toBe('info');
    });

    it('logs a 4xx analysis response at warn', async () => {
      mockFetchError(422, { error: { message: 'bad input' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'validation_error',
      );

      expect(capturedEntries[0].level).toBe('warn');
    });

    it('logs a 5xx analysis response at error', async () => {
      mockFetchError(500, { error: { message: 'server error' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'internal_error',
      );

      expect(capturedEntries[0].level).toBe('error');
    });

    it('logs a 503 readiness probe at error', async () => {
      mockFetchReady(503);

      await expectClientError(
        makeClient().checkReadiness(),
        'provider_unavailable',
      );

      expect(capturedEntries[0].level).toBe('error');
    });

    it('logs a timeout at warn', async () => {
      jest.useFakeTimers();
      mockFetchAborting();

      const client = makeClient();
      const promise = client.post(MINIMAL_REQUEST);
      jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

      await expectClientError(promise, 'timeout');
      expect(capturedEntries[0].level).toBe('warn');
    });

    it('logs a network failure at error', async () => {
      mockFetchThrow(new TypeError('Failed to fetch'));

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );

      expect(capturedEntries[0].level).toBe('error');
    });
  });

  // -----------------------------------------------------------------------
  // Structured content

  describe('structured fields', () => {
    it('tags every entry with the AiEngineClient context', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].context).toBe('AiEngineClient');
    });

    it('uses one constant message for every interaction', async () => {
      // makeClient() clears the captured entries, so each call is inspected
      // before the next client is built. Installing a second fetch mock while a
      // call is in flight would leave the first rejection unobserved.
      const messages: string[] = [];

      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);
      await makeClient().post(MINIMAL_REQUEST);
      messages.push(capturedEntries[0].message);

      mockFetchError(422, { error: { message: 'bad input' } });
      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'validation_error',
      );
      messages.push(capturedEntries[0].message);

      expect(messages).toEqual(['ai_engine_interaction', 'ai_engine_interaction']);
    });

    it('records the operation and path for an analysis call', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].fields.operation).toBe('post');
      expect(capturedEntries[0].fields.path).toBe('/api/v1/code-understanding');
    });

    it('records the operation and path for a readiness probe', async () => {
      mockFetchReady(200);

      await makeClient().checkReadiness();

      expect(capturedEntries[0].fields.operation).toBe('checkReadiness');
      expect(capturedEntries[0].fields.path).toBe('/ready');
    });

    it('records the upstream status when a response was received', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].fields.status).toBe(200);
    });

    it('records the upstream status on a failure response', async () => {
      mockFetchError(503, { error: { message: 'down' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'provider_unavailable',
      );

      expect(capturedEntries[0].fields.status).toBe(503);
    });

    it('omits status when no HTTP response was received', async () => {
      mockFetchThrow(new TypeError('Failed to fetch'));

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );

      expect(capturedEntries[0].fields).not.toHaveProperty('status');
    });

    it('omits status on a timeout', async () => {
      jest.useFakeTimers();
      mockFetchAborting();

      const client = makeClient();
      const promise = client.post(MINIMAL_REQUEST);
      jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

      await expectClientError(promise, 'timeout');
      expect(capturedEntries[0].fields).not.toHaveProperty('status');
    });

    it('records success code and outcome on a successful call', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].fields.code).toBe('success');
      expect(capturedEntries[0].fields.outcome).toBe('success');
    });

    it('records the mapped error code and error outcome on a 4xx', async () => {
      mockFetchError(422, { error: { message: 'bad input' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'validation_error',
      );

      expect(capturedEntries[0].fields.code).toBe('validation_error');
      expect(capturedEntries[0].fields.outcome).toBe('error');
    });

    it('records the mapped error code and error outcome on a 5xx', async () => {
      mockFetchError(504, { error: { message: 'timed out' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'provider_timeout',
      );

      expect(capturedEntries[0].fields.code).toBe('provider_timeout');
      expect(capturedEntries[0].fields.outcome).toBe('error');
    });

    it('records the timeout code on an aborted call', async () => {
      jest.useFakeTimers();
      mockFetchAborting();

      const client = makeClient();
      const promise = client.checkReadiness();
      jest.advanceTimersByTime(TEST_CONFIG.timeoutMs + 100);

      await expectClientError(promise, 'timeout');
      expect(capturedEntries[0].fields.code).toBe('timeout');
      expect(capturedEntries[0].fields.outcome).toBe('error');
    });

    it('records the network_error code on a failed fetch', async () => {
      mockFetchThrow(new TypeError('Failed to fetch'));

      await expectClientError(
        makeClient().checkReadiness(),
        'network_error',
      );

      expect(capturedEntries[0].fields.code).toBe('network_error');
      expect(capturedEntries[0].fields.outcome).toBe('error');
    });

    it('records a finite non-negative duration on success', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      const { durationMs } = capturedEntries[0].fields;
      expect(typeof durationMs).toBe('number');
      expect(Number.isFinite(durationMs)).toBe(true);
      expect(durationMs as number).toBeGreaterThanOrEqual(0);
    });

    it('records a finite non-negative duration on every failure path', async () => {
      const durations: unknown[] = [];

      mockFetchError(500, { error: { message: 'boom' } });
      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'internal_error',
      );
      durations.push(capturedEntries[0].fields.durationMs);

      mockFetchThrow(new TypeError('Failed to fetch'));
      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );
      durations.push(capturedEntries[0].fields.durationMs);

      expect(durations).toHaveLength(2);
      for (const value of durations) {
        expect(Number.isFinite(value)).toBe(true);
        expect(value as number).toBeGreaterThanOrEqual(0);
      }
    });

    it('records a finite duration under fake timers', async () => {
      jest.useFakeTimers();
      mockFetchReady(200);

      await makeClient().checkReadiness();

      const { durationMs } = capturedEntries[0].fields;
      expect(Number.isFinite(durationMs)).toBe(true);
      expect(durationMs as number).toBeGreaterThanOrEqual(0);
    });
  });

  // -----------------------------------------------------------------------
  // Correlation

  describe('request correlation', () => {
    it('records the active correlation ID', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);
      const client = makeClient();

      await runWithCorrelation('req-abc-123', () => client.post(MINIMAL_REQUEST));

      expect(capturedEntries[0].fields.requestId).toBe('req-abc-123');
    });

    it('records the correlation ID on a readiness probe', async () => {
      mockFetchReady(200);
      const client = makeClient();

      await runWithCorrelation('req-ready-1', () => client.checkReadiness());

      expect(capturedEntries[0].fields.requestId).toBe('req-ready-1');
    });

    it('omits the requestId when no correlation context exists', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(capturedEntries[0].fields).not.toHaveProperty('requestId');
    });

    it('does not invent an ID when no context is bound', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      // Only the middleware creates IDs. The client must not fabricate one.
      expect(capturedEntries[0].fields.requestId).toBeUndefined();
    });

    it('keeps each request ID distinct under concurrent load', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);
      const client = makeClient();

      await Promise.all([
        runWithCorrelation('req-a', () => client.post(MINIMAL_REQUEST)),
        runWithCorrelation('req-b', () => client.post(MINIMAL_REQUEST)),
        runWithCorrelation('req-c', () => client.post(MINIMAL_REQUEST)),
      ]);

      expect(capturedEntries).toHaveLength(3);
      // Sorted so the assertion is about the set of IDs, not the order the
      // three concurrent calls happened to log in.
      expect(
        capturedEntries
          .map((e) => e.fields.requestId)
          .sort((a, b) => String(a).localeCompare(String(b))),
      ).toEqual(['req-a', 'req-b', 'req-c']);
    });
  });

  // -----------------------------------------------------------------------
  // Nothing sensitive reaches the sink

  describe('redaction at the client boundary', () => {
    it('never lets the request source_code reach the sink', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      const serialized = JSON.stringify(capturedEntries);
      expect(serialized).not.toContain('source_code');
      expect(serialized).not.toContain('console.log');
    });

    it('never lets a serialised request body reach the sink', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(JSON.stringify(capturedEntries)).not.toContain(
        JSON.stringify(MINIMAL_REQUEST).slice(0, 30),
      );
    });

    it('never lets the response body reach the sink', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      const serialized = JSON.stringify(capturedEntries);
      expect(serialized).not.toContain('A simple log statement');
      expect(serialized).not.toContain('summary');
    });

    it('never lets the raw upstream error message reach the sink', async () => {
      mockFetchError(422, {
        error: {
          code: 'VALIDATION_ERROR',
          message: 'source_code is required and must be non-blank',
        },
      });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'validation_error',
      );

      const serialized = JSON.stringify(capturedEntries);
      expect(serialized).not.toContain('source_code is required');
      expect(serialized).not.toContain('must be non-blank');
      // The controlled code is present even though the free text is not.
      expect(capturedEntries[0].fields.code).toBe('validation_error');
    });

    it('never lets an upstream network error message reach the sink', async () => {
      mockFetchThrow(new TypeError('connect ECONNREFUSED 127.0.0.1:8000'));

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );

      const serialized = JSON.stringify(capturedEntries);
      expect(serialized).not.toContain('ECONNREFUSED');
      expect(serialized).not.toContain('127.0.0.1');
      expect(capturedEntries[0].fields.code).toBe('network_error');
    });

    it('never lets the upstream base URL reach the sink', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      const serialized = JSON.stringify(capturedEntries);
      expect(serialized).not.toContain('test-ai-engine');
      // The path is logged, but never the host it was built from.
      expect(capturedEntries[0].fields.path).toBe('/api/v1/code-understanding');
    });

    it('logs only allowlisted field names', async () => {
      mockFetchError(503, { error: { message: 'down' } });

      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'provider_unavailable',
      );

      expect(Object.keys(capturedEntries[0].fields).sort()).toEqual([
        'code',
        'durationMs',
        'operation',
        'outcome',
        'path',
        'status',
      ]);
    });
  });

  // -----------------------------------------------------------------------
  // Existing behaviour is preserved

  describe('preserved Phase 3 and Phase 5 behaviour', () => {
    it('still POSTs to the unchanged analysis endpoint', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);

      expect(global.fetch).toHaveBeenCalledWith(
        'http://test-ai-engine/api/v1/code-understanding',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('still GETs the unchanged readiness endpoint', async () => {
      mockFetchReady(200);

      await makeClient().checkReadiness();

      expect(global.fetch).toHaveBeenCalledWith(
        'http://test-ai-engine/ready',
        expect.objectContaining({ method: 'GET' }),
      );
    });

    it('still returns the parsed response on success', async () => {
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await expect(makeClient().post(MINIMAL_REQUEST)).resolves.toEqual(
        MINIMAL_RESPONSE,
      );
    });

    it('still throws the same error codes as before', async () => {
      const cases: [number, string][] = [
        [422, 'validation_error'],
        [500, 'internal_error'],
        [502, 'provider_error'],
        [503, 'provider_unavailable'],
        [504, 'provider_timeout'],
      ];

      for (const [status, code] of cases) {
        mockFetchError(status, { error: { message: 'x' } });
        await expectClientError(makeClient().post(MINIMAL_REQUEST), code);
      }
    });

    it('still captures the upstream message on the thrown error', async () => {
      mockFetchError(422, { error: { message: 'source_code is required' } });

      try {
        await makeClient().post(MINIMAL_REQUEST);
        throw new Error('Expected rejection');
      } catch (err: unknown) {
        expect(err).toBeInstanceOf(AiEngineClientError);
        // Preserved for callers; deliberately still not logged.
        expect((err as AiEngineClientError).upstreamMessage).toBe(
          'source_code is required',
        );
      }
    });

    it('still clears the timeout timer on success and on failure', async () => {
      jest.useFakeTimers();
      mockFetchOkWithStatus(200, MINIMAL_RESPONSE);

      await makeClient().post(MINIMAL_REQUEST);
      expect(jest.getTimerCount()).toBe(0);

      mockFetchThrow(new TypeError('Failed to fetch'));
      await expectClientError(
        makeClient().post(MINIMAL_REQUEST),
        'network_error',
      );
      expect(jest.getTimerCount()).toBe(0);
    });

    it('still never parses the readiness response body', async () => {
      const json = mockFetchReady(200);

      await makeClient().checkReadiness();

      expect(json).not.toHaveBeenCalled();
    });
  });
});
