import { jest } from '@jest/globals';

import { AiEngineClient, AiEngineClientError } from './ai-engine.client.js';
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

function makeClient(): AiEngineClient {
  // Construct without NestJS DI — inject config value directly
  return new AiEngineClient(TEST_CONFIG);
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
