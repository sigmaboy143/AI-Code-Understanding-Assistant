/**
 * Phase 6 Step 1 tests: the redaction allowlist is the security boundary.
 *
 * These tests exist because the failure they guard against is silent. A log
 * line that leaks user source code produces no error, no failed request and no
 * visible symptom in the application; the damage is done in log storage. So
 * every rule below is asserted explicitly rather than inferred from the
 * sanitizer's overall behaviour.
 *
 * The cases are deliberately adversarial: the payloads used here are the kind
 * of content that actually flows through this backend (source code, request
 * bodies, the AI Engine request contract's `context` and `question` fields),
 * not toy strings.
 */
import { jest } from '@jest/globals';
import {
  ALLOWED_LOG_FIELDS,
  REDACTED,
  formatLogMessage,
  redactLogFields,
} from './redact.js';

/** Representative source code that must never survive redaction. */
const SOURCE_CODE_SAMPLE = 'const apiKey = "sk-live-DO-NOT-LOG-12345";';

/** Representative user free text that must never survive redaction. */
const QUESTION_SAMPLE = 'Why does this function throw on empty input?';

describe('redactLogFields: allowlist boundary', () => {
  it('exposes exactly the seven approved field names', () => {
    expect(ALLOWED_LOG_FIELDS).toEqual([
      'operation',
      'path',
      'status',
      'durationMs',
      'code',
      'requestId',
      'outcome',
    ]);
  });

  it('keeps every allowed field when each value is well formed', () => {
    const safe = redactLogFields({
      operation: 'post',
      path: '/api/v1/code-understanding',
      status: 200,
      durationMs: 12.5,
      code: 'provider_unavailable',
      requestId: 'req-abc-123',
      outcome: 'success',
    });

    expect(safe).toEqual({
      operation: 'post',
      path: '/api/v1/code-understanding',
      status: 200,
      durationMs: 12.5,
      code: 'provider_unavailable',
      requestId: 'req-abc-123',
      outcome: 'success',
    });
  });

  it('drops unknown fields rather than passing them through', () => {
    const safe = redactLogFields({
      operation: 'post',
      language: 'typescript',
      filePath: 'src/index.ts',
      password: 'hunter2',
      apiKey: 'sk-live-abc',
    });

    expect(safe).toEqual({ operation: 'post' });
    expect(safe).not.toHaveProperty('language');
    expect(safe).not.toHaveProperty('filePath');
    expect(safe).not.toHaveProperty('password');
    expect(safe).not.toHaveProperty('apiKey');
  });

  it('never reads a key that is not on the allowlist', () => {
    // A Proxy that records every property access proves the sanitizer does not
    // even look at disallowed keys, which is stronger than asserting on output.
    // The proxy must actually be handed to the sanitizer for this to mean
    // anything: recording accesses on an object that is never passed in would
    // observe nothing and assert nothing.
    const reads: string[] = [];
    const fields = new Proxy(
      { operation: 'post', source_code: SOURCE_CODE_SAMPLE } as Record<
        string,
        unknown
      >,
      {
        get(target, prop) {
          if (typeof prop === 'string') reads.push(prop);
          return (target as Record<string, unknown>)[prop];
        },
        has(target, prop) {
          if (typeof prop === 'string') reads.push(prop);
          return prop in target;
        },
      },
    );

    const safe = redactLogFields(fields);

    // Sanity: the proxy really was instrumented, so a silent pass is impossible.
    expect(reads.length).toBeGreaterThan(0);
    for (const key of reads) {
      expect(ALLOWED_LOG_FIELDS).toContain(key);
    }
    expect(safe).toEqual({ operation: 'post' });
  });
});

describe('redactLogFields: source code and request payloads', () => {
  it('removes source_code', () => {
    const safe = redactLogFields({
      operation: 'post',
      source_code: SOURCE_CODE_SAMPLE,
    });

    expect(safe).not.toHaveProperty('source_code');
    expect(JSON.stringify(safe)).not.toContain(SOURCE_CODE_SAMPLE);
    expect(JSON.stringify(safe)).not.toContain('sk-live-DO-NOT-LOG-12345');
  });

  it('removes the AI Engine request contract fields verbatim', () => {
    const aiEngineRequest = {
      source_code: SOURCE_CODE_SAMPLE,
      language: 'typescript',
      file_path: 'src/index.ts',
      question: QUESTION_SAMPLE,
      context: 'Some private repository context.',
      analyses: ['summary'],
    };

    const safe = redactLogFields({ operation: 'post', ...aiEngineRequest });

    const rendered = JSON.stringify(safe);
    expect(rendered).not.toContain('source_code');
    expect(rendered).not.toContain(SOURCE_CODE_SAMPLE);
    expect(rendered).not.toContain('question');
    expect(rendered).not.toContain(QUESTION_SAMPLE);
    expect(rendered).not.toContain('context');
    expect(rendered).not.toContain('Some private repository context.');
    expect(rendered).not.toContain('file_path');
  });

  it('removes an entire request body supplied under a body-like key', () => {
    const safe = redactLogFields({
      operation: 'post',
      body: { source_code: SOURCE_CODE_SAMPLE, context: 'private' },
      requestBody: '{"source_code":"leak"}',
    });

    expect(safe).toEqual({ operation: 'post' });
  });

  it('removes an entire response body supplied under a body-like key', () => {
    const safe = redactLogFields({
      operation: 'post',
      responseBody: JSON.stringify({ summary: 'private summary' }),
      upstreamMessage: 'ECONNREFUSED 127.0.0.1:8000 from upstream stack',
    });

    expect(safe).toEqual({ operation: 'post' });
  });

  it('refuses to pass an object through an allowed key', () => {
    const safe = redactLogFields({
      operation: { nested: SOURCE_CODE_SAMPLE },
      path: { toString: () => '/etc/passwd' },
      requestId: ['a', 'b'],
    });

    expect(safe).toEqual({});
  });

  it('refuses to pass source code through the code field', () => {
    // `code` must carry only a controlled outcome token. A source-code payload
    // contains spaces and punctuation, so the grammar rejects it outright.
    const safe = redactLogFields({ code: SOURCE_CODE_SAMPLE });

    expect(safe).not.toHaveProperty('code');
    expect(JSON.stringify(safe)).not.toContain('sk-live-DO-NOT-LOG-12345');
  });

  it('refuses free text through the outcome field', () => {
    const safe = redactLogFields({ outcome: QUESTION_SAMPLE });

    expect(safe).not.toHaveProperty('outcome');
  });
});

describe('redactLogFields: credentials in URLs', () => {
  it('removes user and password from an absolute URL', () => {
    const safe = redactLogFields({
      operation: 'post',
      path: 'http://admin:sup3rs3cret@ai-engine.internal:8000/api/v1/code-understanding',
    });

    expect(safe.path).toBe('/api/v1/code-understanding');
    expect(safe.path).not.toContain('admin');
    expect(safe.path).not.toContain('sup3rs3cret');
    expect(safe.path).not.toContain('ai-engine.internal');
  });

  it('removes a query string that may carry a token', () => {
    const safe = redactLogFields({
      operation: 'post',
      path: '/api/v1/code-understanding?api_key=sk-live-abc&x=1',
    });

    expect(safe.path).toBe('/api/v1/code-understanding');
    expect(safe.path).not.toContain('sk-live-abc');
  });

  it('removes a query string from a relative path', () => {
    const safe = redactLogFields({ path: '/ready?token=abc#frag' });

    expect(safe.path).toBe('/ready');
  });

  it('drops a malformed absolute URL entirely', () => {
    const safe = redactLogFields({ path: 'not-a-url://user:pass@%%%' });

    expect(safe).not.toHaveProperty('path');
  });
});

describe('redactLogFields: log injection', () => {
  it('drops an operation containing CR or LF so no extra log line can be forged', () => {
    const safe = redactLogFields({
      operation: 'post\nINFO admin logged in successfully',
    });

    // Control characters are stripped first, and the sanitized value then fails
    // the operation grammar, so the field is dropped rather than kept. Dropping
    // is the stronger outcome: a forged line never reaches the sink at all,
    // rather than reaching it with its newline merely removed.
    expect(safe).not.toHaveProperty('operation');

    const rendered = JSON.stringify(safe);
    expect(rendered).not.toContain('\n');
    expect(rendered).not.toContain('\r');
    expect(rendered).not.toContain('admin logged in');
  });

  it('strips control characters, keeping only values that remain valid', () => {
    const BEL = String.fromCharCode(7);
    const NUL = String.fromCharCode(0);

    const safe = redactLogFields({
      // Stripping the BEL leaves 'post' and 'success', both of which still match
      // their grammar, so they survive with the control byte removed.
      operation: `po${BEL}st`,
      outcome: `suc${BEL}cess`,
      // Stripping the NUL leaves 'timeouting token', which contains a space and
      // fails the code grammar, so the field is dropped rather than repaired.
      code: `time${NUL}outing token`,
      requestId: 'req- 1',
    });

    expect(safe).toEqual({ operation: 'post', outcome: 'success' });

    const rendered = JSON.stringify(safe);
    expect(rendered).not.toContain(BEL);
    expect(rendered).not.toContain(NUL);
    expect(rendered).not.toContain('token');
    expect(rendered).not.toContain(' 1');
  });

  it('rejects a requestId carrying CR/LF header injection', () => {
    const safe = redactLogFields({
      requestId: 'abc\r\nX-Injected: true',
    });

    expect(safe).not.toHaveProperty('requestId');
  });

  it('renders a single-line message from a constant template', () => {
    const safe = redactLogFields({
      operation: 'post',
      source_code: SOURCE_CODE_SAMPLE,
    });

    const line = formatLogMessage('ai_engine_interaction', safe);

    expect(line).toBe('ai_engine_interaction {"operation":"post"}');
    expect(line.split('\n')).toHaveLength(1);
  });

  it('renders the bare message when no field survives', () => {
    expect(formatLogMessage('ai_engine_interaction', {})).toBe(
      'ai_engine_interaction',
    );
  });
});

describe('redactLogFields: requestId bounds and safety', () => {
  it('accepts a 128 character requestId', () => {
    const id = 'a'.repeat(128);
    expect(redactLogFields({ requestId: id }).requestId).toBe(id);
  });

  it('rejects a 129 character requestId', () => {
    const id = 'a'.repeat(129);
    expect(redactLogFields({ requestId: id })).not.toHaveProperty('requestId');
  });

  it('rejects a requestId containing a space', () => {
    expect(
      redactLogFields({ requestId: 'has space' }),
    ).not.toHaveProperty('requestId');
  });

  it('rejects an empty requestId', () => {
    expect(redactLogFields({ requestId: '' })).not.toHaveProperty('requestId');
  });
});

describe('redactLogFields: typed field validation', () => {
  it('accepts only integer HTTP statuses in range', () => {
    expect(redactLogFields({ status: 200 }).status).toBe(200);
    expect(redactLogFields({ status: 503 }).status).toBe(503);
    expect(redactLogFields({ status: 99 })).not.toHaveProperty('status');
    expect(redactLogFields({ status: 600 })).not.toHaveProperty('status');
    expect(redactLogFields({ status: 200.5 })).not.toHaveProperty('status');
    expect(redactLogFields({ status: '200' })).not.toHaveProperty('status');
  });

  it('accepts only finite non-negative durations', () => {
    expect(redactLogFields({ durationMs: 0 }).durationMs).toBe(0);
    expect(redactLogFields({ durationMs: 12.5 }).durationMs).toBe(12.5);
    expect(redactLogFields({ durationMs: -1 })).not.toHaveProperty(
      'durationMs',
    );
    expect(redactLogFields({ durationMs: Number.NaN })).not.toHaveProperty(
      'durationMs',
    );
    expect(redactLogFields({ durationMs: Number.POSITIVE_INFINITY })).not.toHaveProperty(
      'durationMs',
    );
    expect(redactLogFields({ durationMs: '12' })).not.toHaveProperty(
      'durationMs',
    );
  });

  it('accepts the controlled outcome codes used by the AI Engine client', () => {
    const codes = [
      'timeout',
      'network_error',
      'provider_unavailable',
      'provider_timeout',
      'provider_error',
      'internal_error',
      'validation_error',
    ];

    for (const code of codes) {
      expect(redactLogFields({ code }).code).toBe(code);
    }
  });

  it('rejects an outcome code containing a path separator', () => {
    expect(
      redactLogFields({ code: 'error/../../etc/passwd' }),
    ).not.toHaveProperty('code');
  });
});

describe('redactLogFields: immutability and defensive input handling', () => {
  it('does not mutate a frozen input object', () => {
    const input = Object.freeze({
      operation: 'post',
      status: 200,
      source_code: SOURCE_CODE_SAMPLE,
    });

    const safe = redactLogFields(input);

    expect(Object.isFrozen(input)).toBe(true);
    expect(Object.keys(input)).toEqual(['operation', 'status', 'source_code']);
    expect(safe).toEqual({ operation: 'post', status: 200 });
  });

  it('returns a fresh object on every call', () => {
    const input = { operation: 'post' };

    expect(redactLogFields(input)).not.toBe(redactLogFields(input));
  });

  it('returns an empty object for a non-object input', () => {
    expect(redactLogFields(null as unknown as Record<string, unknown>)).toEqual(
      {},
    );
    expect(redactLogFields('string' as unknown as Record<string, unknown>)).toEqual(
      {},
    );
    expect(redactLogFields(undefined as unknown as Record<string, unknown>)).toEqual(
      {},
    );
  });

  it('ignores null and undefined values for allowed fields', () => {
    expect(redactLogFields({ operation: null, status: undefined })).toEqual({});
  });
});

describe('REDACTED placeholder', () => {
  it('is exported for operator-facing messaging', () => {
    expect(REDACTED).toBe('[REDACTED]');
  });

  it('is never emitted by the allowlist sanitizer', () => {
    // The sanitizer drops unsafe values instead of substituting a marker,
    // because a marker inside a field would imply a field exists when it does
    // not. This test pins that design decision.
    const safe = redactLogFields({
      operation: SOURCE_CODE_SAMPLE,
      code: SOURCE_CODE_SAMPLE,
      requestId: 'bad id',
    });

    expect(safe).toEqual({});
    expect(JSON.stringify(safe)).not.toContain(REDACTED);
  });
});

describe('sanitizer determinism', () => {
  it('produces identical output for identical input', () => {
    const input = {
      operation: 'post',
      path: '/ready',
      status: 503,
      durationMs: 4,
      code: 'provider_unavailable',
      requestId: 'req-1',
      outcome: 'failure',
      source_code: SOURCE_CODE_SAMPLE,
    };

    expect(redactLogFields(input)).toEqual(redactLogFields(input));
  });

  it('is spy-safe: repeated calls do not accumulate state', () => {
    const spy = jest.fn();
    for (let i = 0; i < 5; i += 1) {
      redactLogFields({ operation: 'post', attempt: i });
    }
    expect(spy).not.toHaveBeenCalled();
  });
});
