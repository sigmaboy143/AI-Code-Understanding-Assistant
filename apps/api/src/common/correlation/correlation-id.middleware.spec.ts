/**
 * Phase 6 Step 4 tests for CorrelationIdMiddleware.
 *
 * Three properties are guarded here. The response header is set before the
 * route handler runs, so a handler that fails can still be correlated by the
 * client. The identifier in the async context is the same one returned in the
 * header, so a log line and a client-visible ID always agree. And the
 * middleware emits no log of its own: the invariant is one AI Engine
 * interaction equals one log entry, and a middleware that logged would break it
 * on every single request.
 *
 * Invalid inbound values are asserted to produce a fresh UUID rather than to
 * be passed through, because a header is attacker-controlled and is echoed
 * back into the response.
 */
import { jest } from '@jest/globals';
import { Logger } from '@nestjs/common';
import {
  CorrelationIdMiddleware,
  X_REQUEST_ID_RESPONSE_HEADER,
} from './correlation-id.middleware.js';
import { X_REQUEST_ID_HEADER } from './x-request-id.js';
import { getCorrelationId, runWithCorrelation } from './request-correlation.js';

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

interface RecordedHeader {
  name: string;
  value: string;
}

interface MockResponse {
  headers: RecordedHeader[];
  setHeader(name: string, value: string): void;
}

function mockResponse(): MockResponse {
  return {
    headers: [],
    setHeader(name: string, value: string): void {
      this.headers.push({ name, value });
    },
  };
}

function headersFor(raw: unknown): Record<string, unknown> {
  return { [X_REQUEST_ID_HEADER]: raw };
}

describe('CorrelationIdMiddleware', () => {
  let middleware: CorrelationIdMiddleware;

  beforeEach(() => {
    middleware = new CorrelationIdMiddleware();
  });

  describe('header handling', () => {
    it('echoes a valid inbound ID', () => {
      const response = mockResponse();

      middleware.use(
        { headers: headersFor('req-1') },
        response,
        () => undefined,
      );

      expect(response.headers).toHaveLength(1);
      expect(response.headers[0].value).toBe('req-1');
    });

    it('uses the exact response header name', () => {
      const response = mockResponse();

      middleware.use(
        { headers: headersFor('req-1') },
        response,
        () => undefined,
      );

      expect(response.headers[0].name).toBe(X_REQUEST_ID_RESPONSE_HEADER);
      expect(X_REQUEST_ID_RESPONSE_HEADER).toBe('X-Request-Id');
    });

    it('sets the header before the handler runs', () => {
      const response = mockResponse();
      const seenInsideHandler: RecordedHeader[] = [];

      middleware.use({ headers: headersFor('req-1') }, response, () => {
        seenInsideHandler.push(...response.headers);
      });

      expect(seenInsideHandler).toHaveLength(1);
    });

    it('sets exactly one response header', () => {
      const response = mockResponse();

      middleware.use(
        { headers: headersFor('req-1') },
        response,
        () => undefined,
      );

      expect(response.headers).toHaveLength(1);
    });

    it('calls next exactly once', () => {
      const next = jest.fn();

      middleware.use({ headers: headersFor('req-1') }, mockResponse(), next);

      expect(next).toHaveBeenCalledTimes(1);
    });

    it('calls next with no arguments', () => {
      const next = jest.fn();

      middleware.use({ headers: headersFor('req-1') }, mockResponse(), next);

      expect(next).toHaveBeenCalledWith();
    });
  });

  describe('inbound value handling', () => {
    it('generates a UUID when the header is absent', () => {
      const response = mockResponse();

      middleware.use({ headers: {} }, response, () => undefined);

      expect(UUID_PATTERN.test(response.headers[0].value)).toBe(true);
    });

    it('generates a UUID when the request has no headers object', () => {
      const response = mockResponse();

      middleware.use({}, response, () => undefined);

      expect(UUID_PATTERN.test(response.headers[0].value)).toBe(true);
    });

    it('takes the first element of a repeated header', () => {
      const response = mockResponse();

      // A duplicated header is still a valid inbound value: x-request-id
      // defines the first element as authoritative.
      middleware.use(
        { headers: headersFor(['req-1', 'req-2']) },
        response,
        () => undefined,
      );

      expect(response.headers[0].value).toBe('req-1');
    });

    it('generates a distinct ID per request', () => {
      const seen = new Set<string>();

      for (let i = 0; i < 50; i += 1) {
        const response = mockResponse();
        middleware.use({ headers: {} }, response, () => undefined);
        seen.add(response.headers[0].value);
      }

      expect(seen.size).toBe(50);
    });

    it('accepts an uppercase token', () => {
      const response = mockResponse();

      middleware.use({ headers: headersFor('A.b_c~d-9') }, response, () => undefined);

      expect(response.headers[0].value).toBe('A.b_c~d-9');
    });

    it('accepts a 128 character value at the length limit', () => {
      const raw = 'a'.repeat(128);
      const response = mockResponse();

      middleware.use({ headers: headersFor(raw) }, response, () => undefined);

      expect(response.headers[0].value).toBe(raw);
    });

    const invalidCases: [string, unknown][] = [
      ['CR/LF header injection', 'abc\r\nX-Injected: true'],
      ['a lone LF', 'abc\ndef'],
      ['a lone CR', 'abc\rdef'],
      ['a NUL byte', 'req\u0000123'],
      ['a colon', 'req:123'],
      ['a space', 'req 1'],
      ['a leading space', ' req-1'],
      ['a trailing space', 'req-1 '],
      ['a non-ASCII character', 'req-\u00e91'],
      ['a value one character over the limit', 'a'.repeat(129)],
      ['an empty string', ''],
      ['a number', 42],
      ['null', null],
      ['undefined', undefined],
      ['an object', { id: 'req-1' }],
      ['a boolean', true],
    ];

    for (const [label, raw] of invalidCases) {
      it(`replaces ${label} with a fresh UUID`, () => {
        const response = mockResponse();

        middleware.use({ headers: headersFor(raw) }, response, () => undefined);

        expect(response.headers).toHaveLength(1);
        expect(UUID_PATTERN.test(response.headers[0].value)).toBe(true);
      });
    }

    it('never echoes an invalid value back to the client', () => {
      const response = mockResponse();
      const hostile = 'abc\r\nX-Injected: true';

      middleware.use({ headers: headersFor(hostile) }, response, () => undefined);

      expect(response.headers[0].value).not.toContain('X-Injected');
      expect(response.headers[0].value).not.toContain('\r');
      expect(response.headers[0].value).not.toContain('\n');
    });
  });

  describe('correlation context', () => {
    it('binds the echoed ID for the handler', () => {
      let observed: string | undefined;

      middleware.use(
        { headers: headersFor('req-1') },
        mockResponse(),
        () => {
          observed = getCorrelationId();
        },
      );

      expect(observed).toBe('req-1');
    });

    it('binds the generated ID when the header is absent', () => {
      let observed: string | undefined;
      const response = mockResponse();

      middleware.use({ headers: {} }, response, () => {
        observed = getCorrelationId();
      });

      expect(observed).toBe(response.headers[0].value);
    });

    it('binds the same ID it returns in the header', () => {
      let observed: string | undefined;
      const response = mockResponse();

      middleware.use({ headers: {} }, response, () => {
        observed = getCorrelationId();
      });

      expect(observed).toBe(response.headers[0].value);
      expect(UUID_PATTERN.test(observed ?? '')).toBe(true);
    });

    it('restores the previous context afterwards', () => {
      runWithCorrelation('outer', () => {
        middleware.use(
          { headers: headersFor('req-inner') },
          mockResponse(),
          () => undefined,
        );
        expect(getCorrelationId()).toBe('outer');
      });

      expect(getCorrelationId()).toBeUndefined();
    });

    it('leaves no context behind when the header is absent', () => {
      middleware.use({ headers: {} }, mockResponse(), () => undefined);

      expect(getCorrelationId()).toBeUndefined();
    });

    it('propagates the ID across an await', async () => {
      let observed: string | undefined;

      middleware.use({ headers: headersFor('req-async') }, mockResponse(), () => {
        void (async () => {
          await new Promise((resolve) => setImmediate(resolve));
          observed = getCorrelationId();
        })();
      });

      await new Promise((resolve) => setImmediate(resolve));
      await new Promise((resolve) => setImmediate(resolve));

      expect(observed).toBe('req-async');
    });

    it('does not leak IDs between interleaved requests', async () => {
      const observed: string[] = [];

      // Each request yields a different number of times before finishing, so
      // the three handlers genuinely interleave and complete out of order. The
      // assertion is on isolation, not on completion order, which is a
      // scheduling detail no test should depend on.
      const runOne = (id: string, yields: number): Promise<void> =>
        new Promise<void>((resolve) => {
          middleware.use({ headers: headersFor(id) }, mockResponse(), () => {
            let step = 0;
            const advance = (): void => {
              observed.push(getCorrelationId() ?? '');
              step += 1;
              if (step < yields) {
                setImmediate(advance);
                return;
              }
              resolve();
            };
            advance();
          });
        });

      await Promise.all([
        runOne('req-a', 1),
        runOne('req-b', 2),
        runOne('req-c', 3),
      ]);

      expect(observed).toHaveLength(6);
      // Every observation belongs to its own request, and to no other.
      expect(observed.filter((id) => id === 'req-a')).toHaveLength(1);
      expect(observed.filter((id) => id === 'req-b')).toHaveLength(2);
      expect(observed.filter((id) => id === 'req-c')).toHaveLength(3);
      expect(new Set(observed)).toEqual(new Set(['req-a', 'req-b', 'req-c']));
    });

    it('keeps IDs isolated under concurrency', async () => {
      const observed: (string | undefined)[] = [];
      const labels = ['req-1', 'req-2', 'req-3', 'req-4'];

      await Promise.all(
        labels.map(
          (id) =>
            new Promise<void>((resolve) => {
              middleware.use(
                { headers: headersFor(id) },
                mockResponse(),
                () => {
                  setImmediate(() => {
                    observed.push(getCorrelationId());
                    resolve();
                  });
                },
              );
            }),
        ),
      );

      expect(observed).toHaveLength(4);
      // Every handler saw its own ID and no other, whatever the order the
      // requests happen to complete in.
      expect(new Set(observed)).toEqual(new Set(labels));
    });
  });

  describe('no logging of its own', () => {
    it('emits nothing on the Nest Logger', () => {
      const log = jest.spyOn(Logger.prototype, 'log').mockReturnValue();
      const error = jest.spyOn(Logger.prototype, 'error').mockReturnValue();
      const warn = jest.spyOn(Logger.prototype, 'warn').mockReturnValue();
      const debug = jest.spyOn(Logger.prototype, 'debug').mockReturnValue();
      const verbose = jest.spyOn(Logger.prototype, 'verbose').mockReturnValue();

      middleware.use({ headers: headersFor('req-1') }, mockResponse(), () => undefined);

      // A middleware log on every request would multiply the AI Engine log
      // count and break the one-interaction-one-entry invariant.
      expect(log).not.toHaveBeenCalled();
      expect(error).not.toHaveBeenCalled();
      expect(warn).not.toHaveBeenCalled();
      expect(debug).not.toHaveBeenCalled();
      expect(verbose).not.toHaveBeenCalled();

      log.mockRestore();
      error.mockRestore();
      warn.mockRestore();
      debug.mockRestore();
      verbose.mockRestore();
    });

    it('emits nothing for an invalid header either', () => {
      const log = jest.spyOn(Logger.prototype, 'log').mockReturnValue();
      const warn = jest.spyOn(Logger.prototype, 'warn').mockReturnValue();

      middleware.use(
        { headers: headersFor('abc\r\nX-Injected: true') },
        mockResponse(),
        () => undefined,
      );

      expect(log).not.toHaveBeenCalled();
      expect(warn).not.toHaveBeenCalled();

      log.mockRestore();
      warn.mockRestore();
    });

    it('exposes no logging surface of its own', () => {
      const surface = Object.getOwnPropertyNames(
        CorrelationIdMiddleware.prototype,
      ).filter((name) => name !== 'constructor');

      expect(surface).toEqual(['use']);
    });
  });
});
