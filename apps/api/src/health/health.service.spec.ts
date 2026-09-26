/**
 * Phase 5 health/readiness unit tests.
 *
 * AiEngineClient is replaced with a hand-built stub rather than a NestJS module
 * harness: these tests are about HealthService's own contract — that liveness
 * never probes, and that every readiness failure collapses to one fixed public
 * 503 body — none of which requires booting the container.
 *
 * HTTP-level behaviour (status codes, JSON envelope) is covered separately in
 * health.controller.spec.ts.
 */
import { HttpException, HttpStatus } from '@nestjs/common';
import type { AiEngineClient } from '../analysis/adapters/ai-engine.client.js';
import { AiEngineClientError } from '../analysis/adapters/ai-engine.client.js';
import { HealthService } from './health.service.js';

/** Text a leaky implementation might expose. None of it may reach the client. */
const SENSITIVE_UPSTREAM_TEXT = 'connect ECONNREFUSED 127.0.0.1:8000';

function makeService(checkReadiness: () => Promise<void>): HealthService {
  return new HealthService({ checkReadiness } as unknown as AiEngineClient);
}

/** A probe that must never be invoked; fails loudly if it is. */
function forbiddenProbe(): Promise<void> {
  return Promise.reject(new Error('liveness must not probe the AI Engine'));
}

async function expectNotReady(service: HealthService): Promise<HttpException> {
  try {
    await service.readiness();
  } catch (err: unknown) {
    expect(err).toBeInstanceOf(HttpException);
    return err as HttpException;
  }
  throw new Error('Expected readiness() to reject but it resolved');
}

describe('HealthService.liveness', () => {
  it('returns exactly { status: "ok" }', () => {
    expect(makeService(forbiddenProbe).liveness()).toEqual({ status: 'ok' });
  });

  it('returns no additional keys', () => {
    const result = makeService(forbiddenProbe).liveness();
    expect(Object.keys(result)).toEqual(['status']);
  });

  it('does not call checkReadiness', () => {
    let probeCalls = 0;
    const service = makeService(() => {
      probeCalls += 1;
      return Promise.resolve();
    });

    service.liveness();
    service.liveness();

    expect(probeCalls).toBe(0);
  });

  it('stays available when the AI Engine is unreachable', () => {
    const service = makeService(() =>
      Promise.reject(new AiEngineClientError('network_error', SENSITIVE_UPSTREAM_TEXT)),
    );

    expect(service.liveness()).toEqual({ status: 'ok' });
  });
});

describe('HealthService.readiness', () => {
  it('returns { status: "ready", aiEngine: "ok" } when the probe resolves', async () => {
    const service = makeService(() => Promise.resolve());

    await expect(service.readiness()).resolves.toEqual({
      status: 'ready',
      aiEngine: 'ok',
    });
  });

  it('throws HTTP 503 when the probe rejects', async () => {
    const service = makeService(() =>
      Promise.reject(new AiEngineClientError('provider_unavailable')),
    );

    const error = await expectNotReady(service);
    expect(error.getStatus()).toBe(HttpStatus.SERVICE_UNAVAILABLE);
    expect(error.getStatus()).toBe(503);
  });

  it('exposes exactly the approved 503 body', async () => {
    const service = makeService(() =>
      Promise.reject(new AiEngineClientError('provider_unavailable')),
    );

    const error = await expectNotReady(service);
    expect(error.getResponse()).toEqual({
      status: 'not_ready',
      aiEngine: 'unavailable',
    });
  });

  it('does not expose the upstream error message', async () => {
    const service = makeService(() =>
      Promise.reject(
        new AiEngineClientError('network_error', SENSITIVE_UPSTREAM_TEXT),
      ),
    );

    const error = await expectNotReady(service);
    const body = JSON.stringify(error.getResponse());

    expect(body).not.toContain('ECONNREFUSED');
    expect(body).not.toContain('127.0.0.1');
    expect(body).not.toContain('8000');
    expect(body).not.toContain('network_error');
    expect(body).not.toContain('AiEngineClientError');
  });

  it('normalises every probe failure to the same 503 body', async () => {
    const failures = [
      'timeout',
      'network_error',
      'provider_unavailable',
      'provider_timeout',
      'provider_error',
      'internal_error',
      'validation_error',
    ] as const;

    for (const code of failures) {
      const service = makeService(() =>
        Promise.reject(new AiEngineClientError(code, SENSITIVE_UPSTREAM_TEXT)),
      );

      const error = await expectNotReady(service);

      expect(error.getStatus()).toBe(503);
      expect(error.getResponse()).toEqual({
        status: 'not_ready',
        aiEngine: 'unavailable',
      });
    }
  });

  it('normalises a non-AiEngineClientError to the same 503 body', async () => {
    // Defence in depth: an unexpected internal failure must not bypass
    // normalisation and surface as a 500 with internal detail.
    const service = makeService(() =>
      Promise.reject(new TypeError(SENSITIVE_UPSTREAM_TEXT)),
    );

    const error = await expectNotReady(service);
    expect(error.getStatus()).toBe(503);
    expect(error.getResponse()).toEqual({
      status: 'not_ready',
      aiEngine: 'unavailable',
    });
  });

  it('calls the AI Engine readiness probe', async () => {
    let calls = 0;
    const service = makeService(() => {
      calls += 1;
      return Promise.resolve();
    });

    await service.readiness();
    expect(calls).toBe(1);
  });
});
