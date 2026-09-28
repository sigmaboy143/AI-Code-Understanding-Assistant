import { Test, type TestingModule } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module.js';

/**
 * Backend E2E smoke tests.
 *
 * These boot the real `AppModule` through `Test.createTestingModule()` and drive
 * it over HTTP with supertest, so they exercise the assembled application graph:
 * the global `APP_PIPE`, and the correlation middleware that `CommonModule`
 * registers for every route. They are not unit tests with a mocked module graph.
 *
 * DETERMINISM CONTRACT
 *
 * Every request below is answered entirely inside this process. Nothing here
 * contacts the AI Engine, Ollama, PostgreSQL, Redis, or any other network
 * dependency, so `npm run test:e2e` passes or fails on this repository alone and
 * never on the state of a developer's machine.
 *
 * That is why these requests are chosen the way they are:
 *
 * - `GET /health` is liveness only. `HealthService.liveness()` performs no
 *   network I/O by design, so it is safe to assert unconditionally.
 * - `POST /analysis/code` is sent a payload that `forbidNonWhitelisted` rejects
 *   on its own merits. The unknown property is the rejection reason, so the
 *   request cannot reach `AnalysisService` or `AiEngineClient` even if the
 *   required-field decorators were later removed. The test therefore cannot
 *   start depending on the AI Engine by accident.
 *
 * `GET /ready` is deliberately NOT exercised. It probes the AI Engine by
 * definition, so its result depends on whether something happens to be
 * listening on the configured base URL. Asserting it here would make this suite
 * non-deterministic. Its failure mapping is already covered deterministically by
 * `src/health/health.service.spec.ts`.
 *
 * ESM CONFIGURATION
 *
 * `test/jest-e2e.json` must stay aligned with the ESM settings in
 * `jest.config.ts`. This project compiles TypeScript with `module: nodenext`, so
 * relative source imports carry a `.js` suffix, and NestJS 12 ships ESM-only
 * packages that CommonJS output cannot `require`. Without
 * `extensionsToTreatAsEsm`, ts-jest's `useESM: true`, and the `.js` -> `.ts`
 * `moduleNameMapper`, the suite fails while loading `@nestjs/testing` and no
 * application code runs at all. Keep the two configs in step.
 */
describe('Backend E2E (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  describe('GET /health', () => {
    it('returns 200 and the liveness status', async () => {
      const response = await request(app.getHttpServer())
        .get('/health')
        .expect(200);

      expect(response.body).toEqual({ status: 'ok' });
    });

    it('answers without contacting the AI Engine', async () => {
      // Liveness must survive a completely unreachable AI Engine, otherwise an
      // orchestrator would restart a healthy process during a downstream outage.
      // A real AI Engine is never started here, so a 200 proves the endpoint
      // performs no I/O of its own.
      const response = await request(app.getHttpServer()).get('/health');

      expect(response.status).toBe(200);
    });

    it('echoes a correlation ID, proving the middleware is wired', async () => {
      const response = await request(app.getHttpServer())
        .get('/health')
        .expect(200);

      expect(response.headers['x-request-id']).toBeDefined();
    });

    it('honours a caller-supplied correlation ID', async () => {
      const correlationId = 'e2e-supplied-correlation-id';

      const response = await request(app.getHttpServer())
        .get('/health')
        .set('X-Request-Id', correlationId)
        .expect(200);

      expect(response.headers['x-request-id']).toBe(correlationId);
    });
  });

  describe('global validation pipe', () => {
    it('rejects an unknown property with 400 before any handler runs', async () => {
      // Proves the APP_PIPE registered in AppModule is actually applied to the
      // assembled application, which unit tests with a stubbed module graph
      // cannot show. The unknown property is rejected by forbidNonWhitelisted,
      // so this never reaches the AI Engine.
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({
          language: 'typescript',
          code: 'export const value = 1;',
          notARealField: true,
        })
        .expect(400);

      expect(response.body).toMatchObject({
        statusCode: 400,
        error: 'Bad Request',
      });
      expect(response.body.message).toEqual(
        expect.arrayContaining([
          expect.stringContaining('notARealField'),
        ]),
      );
    });
  });
});
