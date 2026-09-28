/**
 * Phase 6 Step 3 tests for inbound X-Request-Id validation.
 *
 * The rejection cases use the actual attack shapes: CRLF header injection,
 * an oversized value, embedded whitespace, NUL and other C0 bytes, and a
 * repeated header arriving as an array. Each must be replaced by a fresh UUID
 * rather than sanitized, because a generated ID is always safe whereas a
 * partially cleaned attacker string is not provably safe.
 */
import {
  MAX_REQUEST_ID_LENGTH,
  REQUEST_ID_PATTERN,
  X_REQUEST_ID_HEADER,
  isValidRequestId,
  resolveRequestId,
  toHeaderCandidate,
} from './x-request-id.js';

/** RFC 4122 version 4 UUID shape. */
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('constants', () => {
  it('uses the lower-cased header name Node normalises to', () => {
    expect(X_REQUEST_ID_HEADER).toBe('x-request-id');
  });

  it('declares a 128 character maximum', () => {
    expect(MAX_REQUEST_ID_LENGTH).toBe(128);
  });

  it('anchors the pattern at both ends so no partial match is possible', () => {
    expect(REQUEST_ID_PATTERN.source).toBe('^[A-Za-z0-9._~-]{1,128}$');
  });
});

describe('isValidRequestId: accepted values', () => {
  it.each([
    ['a simple id', 'req-123'],
    ['a UUID', '3f2504e0-4f89-41d3-9a0c-0305e82c3301'],
    ['dots', 'req.1.2.3'],
    ['underscores', 'req_1_2'],
    ['tildes', 'req~1~2'],
    ['mixed case', 'Req-ABC_123'],
    ['a single character', 'a'],
    ['128 characters', 'a'.repeat(128)],
    ['digits only', '1234567890'],
  ])('accepts %s', (_label, value) => {
    expect(isValidRequestId(value)).toBe(true);
  });
});

describe('isValidRequestId: rejected values', () => {
  it.each([
    ['an empty string', ''],
    ['a single space', ' '],
    ['leading and trailing whitespace', ' req-123 '],
    ['an embedded space', 'has space'],
    ['a tab', 'req\t123'],
    ['a carriage return', 'req\r123'],
    ['a line feed', 'req\n123'],
    ['a CRLF header injection attempt', 'abc\r\nX-Injected: true'],
    ['a lone LF injection attempt', 'abc\n{"level":"info"}'],
    ['a NUL byte', 'req\u0000123'],
    ['a 129 character value', 'a'.repeat(129)],
    ['a 200 character value', 'b'.repeat(200)],
    ['a colon', 'req:123'],
    ['a semicolon', 'req;123'],
    ['a comma', 'req,123'],
    ['a slash', 'req/123'],
    ['a backslash', 'req\\123'],
    ['an at sign', 'req@123'],
    ['a percent sign', 'req%0d%0a'],
    ['angle brackets', '<script>'],
    ['a non-ASCII character', 'req-é'],
    ['an emoji', 'req-\u{1F600}'],
  ])('rejects %s', (_label, value) => {
    expect(isValidRequestId(value)).toBe(false);
  });

  it.each([
    ['undefined', undefined],
    ['null', null],
    ['a number', 12345],
    ['an object', {}],
    ['an array of strings', ['req-1']],
  ])('rejects %s', (_label, value) => {
    expect(isValidRequestId(value)).toBe(false);
  });
});

describe('toHeaderCandidate', () => {
  it('passes a string through unchanged', () => {
    expect(toHeaderCandidate('req-1')).toBe('req-1');
  });

  it('takes the first element of a repeated header', () => {
    expect(toHeaderCandidate(['req-1', 'req-2'])).toBe('req-1');
  });

  it('returns undefined for an empty repeated header', () => {
    expect(toHeaderCandidate([])).toBeUndefined();
  });

  it('passes a missing header through as undefined', () => {
    expect(toHeaderCandidate(undefined)).toBeUndefined();
  });
});

describe('resolveRequestId: honours a valid supplied ID', () => {
  it('returns the supplied ID verbatim', () => {
    expect(resolveRequestId('req-abc-123')).toBe('req-abc-123');
  });

  it('returns a 128 character supplied ID verbatim', () => {
    const id = 'z'.repeat(128);
    expect(resolveRequestId(id)).toBe(id);
  });
});

describe('resolveRequestId: replaces anything invalid', () => {
  it.each([
    ['a missing header', undefined],
    ['an empty header', ''],
    ['a whitespace header', '   '],
    ['a CRLF injection header', 'abc\r\nX-Injected: true'],
    ['a LF injection header', 'abc\ndef'],
    ['a 200 character header', 'c'.repeat(200)],
    ['a control character header', 'req\u0000123'],
    ['a colon-bearing header', 'req:123'],
    ['a non-ASCII header', 'req-é'],
    ['an array header', ['req-1', 'req-2']],
  ])('generates a fresh UUID for %s', (_label, value) => {
    const resolved = resolveRequestId(value);

    expect(UUID_PATTERN.test(resolved)).toBe(true);
    expect(resolved).not.toBe(value);
  });

  it('never propagates an invalid supplied value', () => {
    const resolved = resolveRequestId('bad id\r\nevil: true');

    expect(resolved).not.toContain(' ');
    expect(resolved).not.toContain('\r');
    expect(resolved).not.toContain('\n');
  });
});

describe('resolveRequestId: generation behaviour', () => {
  it('generates a distinct ID on each call', () => {
    const ids = new Set(Array.from({ length: 50 }, () => resolveRequestId(undefined)));

    expect(ids.size).toBe(50);
  });

  it('generates a v4 UUID', () => {
    expect(resolveRequestId(undefined)).toMatch(UUID_PATTERN);
  });

  it('always returns a value the sanitizer would accept', () => {
    // The generated ID must itself satisfy the allowlist, otherwise it would be
    // dropped by the log redactor and the log line would lose its correlation.
    for (let i = 0; i < 20; i += 1) {
      expect(isValidRequestId(resolveRequestId(undefined))).toBe(true);
    }
  });
});
