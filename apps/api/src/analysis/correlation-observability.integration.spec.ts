/**
 * Phase 6 permanent end-to-end correlation proof.
 *
 * Every other Phase 6 suite proves one link in isolation: the middleware sets a
 * header, AnalysisService falls back correctly, the client logs structured
 * fields. None of them proves the three agree on the same request, which is the
 * only property that makes correlation useful. If a future edit changed the
 * middleware to mint a second ID, or the client to read a stale context, every
 * existing test would still pass and the bug would ship.
 *
 * So this suite boots the real AppModule, drives real HTTP through supertest,
 * and asserts the three-way equality:
 *
 *     X-Request-Id response header
 *       === AnalysisResult.requestId
 *       === AI Engine client log requestId
 *
 * The AI Engine is never contacted. The native fetch path is mocked using the
 * same convention as the Phase 3 client suite, and LOG_SINK is overridden so log
 * entries are captured deterministically rather than scraped from stdout.
 */
import { jest } from '@jest/globals';
import 'reflect-metadata';
import type { INestApplication } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../app.module.js';
import {
  LOG_SINK,
  type LogEntry,
  type LogSink,
} from '../common/logging/log-sink.js';
import type { AiEngineResponseContract } from './contracts/ai-engine-response.contract.js';

/**
 * The Phase 3 AI Engine response fixture, unchanged.
 *
 * Copied rather than imported because a spec must not import from another spec.
 * It is typed by the real contract, so if either side of the frozen AI Engine
 * contract changes this file stops compiling rather than drifting silently.
 */
const AI_ENGINE_RESPONSE: AiEngineResponseContract = {
  summary: 'A simple log statement.',
  metadata: { language: 'typescript', file_path: null, analyses: [] },
  confidence: { level: 'LOW', evidence: [], notes: '' },
  explanation: null,
  structure: null,
  dependencies: null,
  improvements: null,
};

/** Distinctive strings that must never appear in any captured log entry. */
const CODE_CANARY = 'phase6-code-canary-9f3a';
const CONTEXT_CANARY = 'phase6-context-canary-7b2e';

/** The correlation-ID grammar, mirroring x-request-id.ts. */
const ID_PATTERN = /^[A-Za-z0-9._~-]{1,128}$/;

const AI_INTERACTION_MESSAGE = 'ai_engine_interaction';

const capturedEntries: LogEntry[] = [];

const capturingSink: LogSink = {
  log: (entry: LogEntry): void => {
    capturedEntries.push(entry);
  },
};

function mockFetchOk(body: unknown = AI_ENGINE_RESPONSE): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response);
}

/** All AI Engine interaction entries recorded for one correlation ID. */
function interactionsFor(requestId: string): LogEntry[] {
  return capturedEntries.filter(
    (entry) =>
      entry.message === AI_INTERACTION_MESSAGE &&
      entry.fields.requestId === requestId,
  );
}

/** The exact JSON body the adapter produces for AI_ENGINE_RESPONSE. */
function expectedAnalysisBody(requestId: string): Record<string, unknown> {
  return {
    requestId,
    language: 'typescript',
    symbols: [],
    relationships: [],
    summary: 'A simple log statement.',
    // score, model and reasoning are undefined in the adapter and therefore
    // absent from the serialised body. Only the normalised level survives.
    confidence: { level: 'low' },
    evidence: [],
    analysedAt: expect.any(String) as unknown,
  };
}

describe('Phase 6 correlation and observability (end to end)', () => {
  let app: INestApplication;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(LOG_SINK)
      .useValue(capturingSink)
      .compile();

    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    capturedEntries.length = 0;
    mockFetchOk();
  });

  describe('the correlation ID reaches all three consumers', () => {
    it('returns the inbound ID in the header, the result and the client log', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      expect(response.status).toBe(201);
      expect(response.headers['x-request-id']).toBe('integration-request-1');
      expect(response.body.requestId).toBe('integration-request-1');

      const interactions = interactionsFor('integration-request-1');
      expect(interactions).toHaveLength(1);
      expect(interactions[0].fields.requestId).toBe('integration-request-1');
    });

    it('records exactly one AI interaction for the request', async () => {
      await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      const all = capturedEntries.filter(
        (entry) => entry.message === AI_INTERACTION_MESSAGE,
      );

      expect(all).toHaveLength(1);
      expect(all[0].context).toBe('AiEngineClient');
      expect(all[0].level).toBe('info');
      expect(all[0].fields.operation).toBe('post');
      expect(all[0].fields.path).toBe('/api/v1/code-understanding');
      expect(all[0].fields.status).toBe(200);
      expect(all[0].fields.code).toBe('success');
      expect(all[0].fields.outcome).toBe('success');
      expect(typeof all[0].fields.durationMs).toBe('number');
    });

    it('keeps the header, the result and the log in exact agreement', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      const fromHeader = response.headers['x-request-id'] as string;
      const fromResult = response.body.requestId as string;
      const fromLog = interactionsFor(fromHeader)[0].fields
        .requestId as string;

      expect(fromResult).toBe(fromHeader);
      expect(fromLog).toBe(fromHeader);
    });
  });

  describe('generated and replaced correlation IDs', () => {
    it('generates a valid ID when the header is absent', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      expect(response.status).toBe(201);
      const header = response.headers['x-request-id'] as string;
      expect(header).toMatch(ID_PATTERN);
      // The generated ID must be the one used everywhere else, not a new one.
      expect(response.body.requestId).toBe(header);
      expect(interactionsFor(header)).toHaveLength(1);
    });

    it('replaces an invalid inbound ID and uses the replacement downstream', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'not a valid id!!')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      expect(response.status).toBe(201);
      const header = response.headers['x-request-id'] as string;
      expect(header).not.toBe('not a valid id!!');
      expect(header).toMatch(ID_PATTERN);
      expect(response.body.requestId).toBe(header);
      expect(interactionsFor(header)).toHaveLength(1);
    });

    it('replaces an over-long inbound ID rather than truncating it', async () => {
      const hostile = 'a'.repeat(200);

      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', hostile)
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      const header = response.headers['x-request-id'] as string;
      expect(header).not.toBe(hostile);
      expect(header).toMatch(ID_PATTERN);
      expect(interactionsFor(header)).toHaveLength(1);
    });
  });

  describe('concurrent isolation', () => {
    it('keeps two concurrent requests entirely separate', async () => {
      const ids = ['concurrent-req-a', 'concurrent-req-b'];

      // No assertion on completion order: only on per-request agreement.
      const responses = await Promise.all(
        ids.map((id) =>
          request(app.getHttpServer())
            .post('/analysis/code')
            .set('X-Request-Id', id)
            .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` }),
        ),
      );

      for (const [index, response] of responses.entries()) {
        const expected = ids[index];

        expect(response.status).toBe(201);
        expect(response.headers['x-request-id']).toBe(expected);
        expect(response.body.requestId).toBe(expected);
        expect(interactionsFor(expected)).toHaveLength(1);
      }

      // Neither request observed the other's ID anywhere.
      expect(interactionsFor(ids[0])[0].fields.requestId).not.toBe(ids[1]);
      expect(interactionsFor(ids[1])[0].fields.requestId).not.toBe(ids[0]);
    });

    it('keeps three concurrent requests with no header separate', async () => {
      const responses = await Promise.all(
        Array.from({ length: 3 }, () =>
          request(app.getHttpServer())
            .post('/analysis/code')
            .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` }),
        ),
      );

      const headers = responses.map(
        (response) => response.headers['x-request-id'] as string,
      );

      expect(new Set(headers).size).toBe(3);
      for (const [index, response] of responses.entries()) {
        expect(response.body.requestId).toBe(headers[index]);
        expect(interactionsFor(headers[index])).toHaveLength(1);
      }
    });
  });

  describe('liveness performs no AI interaction', () => {
    it('answers GET /health with the unchanged body and logs nothing', async () => {
      capturedEntries.length = 0;

      const response = await request(app.getHttpServer()).get('/health');

      expect(response.status).toBe(200);
      expect(response.body).toEqual({ status: 'ok' });
      expect(
        capturedEntries.filter(
          (entry) => entry.message === AI_INTERACTION_MESSAGE,
        ),
      ).toHaveLength(0);
    });

    it('still logs exactly one interaction for the readiness probe', async () => {
      // The contrast matters: /health does no I/O, while /ready genuinely calls
      // the AI Engine and therefore produces exactly one interaction log. If
      // /health ever started probing, the assertion above would fail.
      capturedEntries.length = 0;

      const response = await request(app.getHttpServer()).get('/ready');

      expect(response.status).toBe(200);
      const interactions = capturedEntries.filter(
        (entry) => entry.message === AI_INTERACTION_MESSAGE,
      );
      expect(interactions).toHaveLength(1);
      expect(interactions[0].fields.operation).toBe('checkReadiness');
    });
  });

  describe('response body is unchanged', () => {
    it('returns the exact Phase 5 analysis body', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      expect(response.body).toEqual(
        expectedAnalysisBody('integration-request-1'),
      );
    });

    it('adds no keys to the analysis response body', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      // The only Phase 6 transport addition is the X-Request-Id header, so the
      // body key set must be exactly what the adapter produces.
      expect(Object.keys(response.body).sort()).toEqual([
        'analysedAt',
        'confidence',
        'evidence',
        'language',
        'relationships',
        'requestId',
        'summary',
        'symbols',
      ]);
      expect(Object.keys(response.body.confidence)).toEqual(['level']);
    });

    it('emits a valid ISO timestamp for analysedAt', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      expect(String(response.body.analysedAt)).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
      );
    });
  });

  describe('nothing sensitive reaches the log sink', () => {
    it('never logs the source code, context or any request field', async () => {
      await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({
          language: 'typescript',
          code: `const x = '${CODE_CANARY}';`,
          filePath: 'src/index.ts',
          context: CONTEXT_CANARY,
        });

      const serialised = JSON.stringify(capturedEntries);

      expect(capturedEntries.length).toBeGreaterThan(0);
      expect(serialised).not.toContain(CODE_CANARY);
      expect(serialised).not.toContain(CONTEXT_CANARY);
      expect(serialised).not.toContain('source_code');
      expect(serialised).not.toContain('src/index.ts');
      expect(serialised).not.toContain('question');
      expect(serialised).not.toContain('upstreamMessage');
    });

    it('never logs the AI Engine response body', async () => {
      await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      const serialised = JSON.stringify(capturedEntries);

      expect(serialised).not.toContain('A simple log statement.');
      expect(serialised).not.toContain('metadata');
      expect(serialised).not.toContain('explanation');
    });

    it('never logs the raw upstream message on a failure', async () => {
      const upstreamMessage = 'source_code is required and must be non-blank';
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            error: { code: 'VALIDATION_ERROR', message: upstreamMessage },
          }),
      } as unknown as Response);

      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      // The adapter maps this to a 400 with a fixed public message.
      expect(response.status).toBe(400);

      const serialised = JSON.stringify(capturedEntries);
      expect(serialised).not.toContain(upstreamMessage);
      expect(serialised).not.toContain('VALIDATION_ERROR');
      // The controlled code is still recorded, which is the point of the map.
      expect(interactionsFor('integration-request-1')).toHaveLength(1);
      expect(interactionsFor('integration-request-1')[0].fields.code).toBe(
        'validation_error',
      );
    });

    it('logs only allowlisted field names', async () => {
      await request(app.getHttpServer())
        .post('/analysis/code')
        .set('X-Request-Id', 'integration-request-1')
        .send({ language: 'typescript', code: `const x = '${CODE_CANARY}';` });

      for (const entry of capturedEntries) {
        for (const key of Object.keys(entry.fields)) {
          expect([
            'operation',
            'path',
            'status',
            'durationMs',
            'code',
            'requestId',
            'outcome',
          ]).toContain(key);
        }
      }
    });
  });
});
