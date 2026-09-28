/**
 * Phase 5 health/readiness integration tests.
 *
 * These boot the real AppModule and drive real HTTP requests, so they prove the
 * thing unit tests structurally cannot: that /health and /ready are actually
 * registered, routed, and wired to a working HealthService through the DI graph.
 *
 * AiEngineClient is replaced with a small fake rather than mocking global fetch.
 * That keeps the test independent of the HTTP implementation — it asserts the
 * controller/module contract, not how the probe happens to be transported.
 * `health.service.spec.ts` and `ai-engine.client.spec.ts` already cover the
 * transport layer in isolation.
 *
 * ANALYSIS_PROVIDER is also replaced with a fake that throws if invoked, so an
 * accidental analysis call fails loudly instead of reaching a real AI Engine.
 * No network I/O occurs anywhere in this suite.
 */
import { jest } from '@jest/globals';
import type { INestApplication } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../app.module.js';
import type { AnalysisRequest } from '../analysis/interfaces/analysis-provider.interface.js';
import { ANALYSIS_PROVIDER } from '../analysis/interfaces/analysis-provider.interface.js';
import type { AnalysisResult } from '../analysis/models/analysis-result.model.js';
import { AiEngineClient, AiEngineClientError } from '../analysis/adapters/ai-engine.client.js';

/** Sensitive transport detail a leaky implementation might echo back. */
const SENSITIVE_UPSTREAM_TEXT =
  'fetch failed: connect ECONNREFUSED 127.0.0.1:8000';

const LIVENESS_BODY = { status: 'ok' };
const READY_BODY = { status: 'ready', aiEngine: 'ok' };
const NOT_READY_BODY = { status: 'not_ready', aiEngine: 'unavailable' };

const checkReadiness = jest.fn(async (): Promise<void> => {});

const fakeAiEngineClient = { checkReadiness } as unknown as AiEngineClient;

const fakeAnalysisProvider = {
  analyzeCode: async (_request: AnalysisRequest): Promise<AnalysisResult> => {
    throw new Error('ANALYSIS_PROVIDER must not be called by health endpoints');
  },
};

describe('Health endpoints (Phase 5 integration)', () => {
  let app: INestApplication;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(AiEngineClient)
      .useValue(fakeAiEngineClient)
      .overrideProvider(ANALYSIS_PROVIDER)
      .useValue(fakeAnalysisProvider)
      .compile();

    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    checkReadiness.mockClear();
    checkReadiness.mockImplementation(async () => {});
  });

  // ---------------------------------------------------------------------
  // GET /health — liveness
  // ---------------------------------------------------------------------

  describe('GET /health', () => {
    it('returns HTTP 200 with exactly { status: "ok" }', async () => {
      const response = await request(app.getHttpServer()).get('/health');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(LIVENESS_BODY);
    });

    it('never returns 201', async () => {
      const response = await request(app.getHttpServer()).get('/health');

      expect(response.status).not.toBe(201);
    });

    it('stays HTTP 200 when the AI Engine readiness probe would fail', async () => {
      checkReadiness.mockImplementation(async () => {
        throw new AiEngineClientError('network_error', SENSITIVE_UPSTREAM_TEXT);
      });

      const response = await request(app.getHttpServer()).get('/health');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(LIVENESS_BODY);
    });

    it('does not invoke the AI Engine readiness probe at all', async () => {
      await request(app.getHttpServer()).get('/health');
      await request(app.getHttpServer()).get('/health');

      expect(checkReadiness).not.toHaveBeenCalled();
    });

    it('leaks nothing about the AI Engine', async () => {
      checkReadiness.mockImplementation(async () => {
        throw new AiEngineClientError('network_error', SENSITIVE_UPSTREAM_TEXT);
      });

      const response = await request(app.getHttpServer()).get('/health');
      const text = response.text;

      expect(text).not.toContain('ECONNREFUSED');
      expect(text).not.toContain('127.0.0.1');
      expect(text).not.toContain('8000');
      expect(text).not.toContain('aiEngine');
      expect(text).not.toContain('not_ready');
    });
  });

  // ---------------------------------------------------------------------
  // GET /ready — readiness
  // ---------------------------------------------------------------------

  describe('GET /ready', () => {
    it('returns HTTP 200 with the ready body when the AI Engine is ready', async () => {
      const response = await request(app.getHttpServer()).get('/ready');

      expect(response.status).toBe(200);
      expect(response.body).toEqual(READY_BODY);
    });

    it('never returns 201', async () => {
      const response = await request(app.getHttpServer()).get('/ready');

      expect(response.status).not.toBe(201);
    });

    it('calls the AI Engine readiness probe exactly once', async () => {
      await request(app.getHttpServer()).get('/ready');

      expect(checkReadiness).toHaveBeenCalledTimes(1);
    });

    it('returns HTTP 503 with the not_ready body when the probe rejects', async () => {
      checkReadiness.mockImplementation(async () => {
        throw new AiEngineClientError('provider_unavailable');
      });

      const response = await request(app.getHttpServer()).get('/ready');

      expect(response.status).toBe(503);
      expect(response.body).toEqual(NOT_READY_BODY);
    });

    it('returns exactly the not_ready body with no extra envelope keys', async () => {
      checkReadiness.mockImplementation(async () => {
        throw new AiEngineClientError('provider_unavailable');
      });

      const response = await request(app.getHttpServer()).get('/ready');

      // Proves the 503 is not wrapped in NestJS's default
      // { statusCode, message } envelope.
      expect(Object.keys(response.body).sort()).toEqual([
        'aiEngine',
        'status',
      ]);
      expect(response.body).not.toHaveProperty('statusCode');
      expect(response.body).not.toHaveProperty('message');
    });

    it('returns HTTP 503 for every probe failure mode', async () => {
      const failures = [
        'timeout',
        'network_error',
        'provider_unavailable',
        'provider_timeout',
        'provider_error',
        'internal_error',
      ] as const;

      for (const code of failures) {
        checkReadiness.mockImplementation(async () => {
          throw new AiEngineClientError(code, SENSITIVE_UPSTREAM_TEXT);
        });

        const response = await request(app.getHttpServer()).get('/ready');

        expect(response.status).toBe(503);
        expect(response.body).toEqual(NOT_READY_BODY);
      }
    });

    it('exposes no internal detail in the 503 response', async () => {
      checkReadiness.mockImplementation(async () => {
        throw new AiEngineClientError('network_error', SENSITIVE_UPSTREAM_TEXT);
      });

      const response = await request(app.getHttpServer()).get('/ready');
      const text = response.text;

      expect(response.status).toBe(503);
      expect(text).not.toContain('ECONNREFUSED');
      expect(text).not.toContain('127.0.0.1');
      expect(text).not.toContain('8000');
      expect(text).not.toContain('fetch failed');
      expect(text).not.toContain('network_error');
      expect(text).not.toContain('AiEngineClientError');
      expect(text).not.toContain('statusCode');
      expect(text).not.toContain('message');
      expect(text).not.toContain('    at ');
    });
  });
});
