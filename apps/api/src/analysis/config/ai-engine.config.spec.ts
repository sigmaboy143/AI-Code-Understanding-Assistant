import { createAiEngineConfig } from './ai-engine.config.js';

// ---------------------------------------------------------------------------
// Helpers

const ENV_KEYS = ['AI_ENGINE_BASE_URL', 'AI_ENGINE_TIMEOUT_MS'] as const;

const saved: Record<string, string | undefined> = {};

/**
 * `createAiEngineConfig` reads process.env at call time, so each test only has
 * to clear the two variables it cares about and restore whatever was there
 * afterwards. Nothing else in the environment is observed.
 */
function clearAiEngineEnv(): void {
  for (const key of ENV_KEYS) {
    saved[key] = process.env[key];
    delete process.env[key];
  }
}

beforeEach(() => {
  clearAiEngineEnv();
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    const value = saved[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
});

// ---------------------------------------------------------------------------
// Defaults

describe('createAiEngineConfig defaults', () => {
  it('defaults the request timeout to 60000ms', () => {
    // A real analysis completed in 34.3s, so the previous 10s default could
    // never have succeeded against a live provider. This assertion exists to
    // stop that value from being reintroduced silently.
    expect(createAiEngineConfig().timeoutMs).toBe(60_000);
  });

  it('keeps the default timeout long enough for the observed runtime', () => {
    const OBSERVED_LATENCY_MS = 34_300;

    expect(createAiEngineConfig().timeoutMs).toBeGreaterThan(OBSERVED_LATENCY_MS);
  });

  it('does not exceed the AI Engine REQUEST_TIMEOUT budget', () => {
    // The AI Engine gives up on the provider at 60s, so a larger NestJS-side
    // budget would only mean waiting past the point of guaranteed failure.
    const AI_ENGINE_REQUEST_TIMEOUT_MS = 60_000;

    expect(createAiEngineConfig().timeoutMs).toBeLessThanOrEqual(
      AI_ENGINE_REQUEST_TIMEOUT_MS,
    );
  });

  it('defaults the base URL to the local development origin', () => {
    expect(createAiEngineConfig().baseUrl).toBe('http://127.0.0.1:8000');
  });
});

// ---------------------------------------------------------------------------
// Environment overrides

describe('createAiEngineConfig environment overrides', () => {
  it('uses AI_ENGINE_TIMEOUT_MS when it is set', () => {
    process.env['AI_ENGINE_TIMEOUT_MS'] = '5000';

    expect(createAiEngineConfig().timeoutMs).toBe(5000);
  });

  it('accepts a timeout larger than the default', () => {
    process.env['AI_ENGINE_TIMEOUT_MS'] = '90000';

    expect(createAiEngineConfig().timeoutMs).toBe(90_000);
  });

  it('parses the timeout as a number rather than a string', () => {
    process.env['AI_ENGINE_TIMEOUT_MS'] = '1500';

    expect(typeof createAiEngineConfig().timeoutMs).toBe('number');
  });

  it('uses AI_ENGINE_BASE_URL when it is set', () => {
    process.env['AI_ENGINE_BASE_URL'] = 'http://ai-engine.internal:8000';

    expect(createAiEngineConfig().baseUrl).toBe('http://ai-engine.internal:8000');
  });

  it('keeps base URL and timeout independently overridable', () => {
    process.env['AI_ENGINE_BASE_URL'] = 'http://ai-engine.internal:8000';
    process.env['AI_ENGINE_TIMEOUT_MS'] = '12345';

    expect(createAiEngineConfig()).toEqual({
      baseUrl: 'http://ai-engine.internal:8000',
      timeoutMs: 12_345,
    });
  });
});
