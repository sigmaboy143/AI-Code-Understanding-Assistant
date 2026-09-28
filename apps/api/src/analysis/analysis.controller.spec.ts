/**
 * Phase 4 integration test: proves the global APP_PIPE registered in AppModule
 * actually rejects malformed HTTP requests BEFORE the analysis provider runs.
 *
 * Why this is an integration test and not a DTO unit test: the DTO specs call
 * class-validator directly, which proves the decorators work but says nothing
 * about whether the pipe is wired into the running application. This test boots
 * the real AppModule and drives real HTTP requests through supertest, so it
 * covers the wiring itself. It also asserts the provider's call count, which is
 * the only way to prove rejection happened upstream of the provider rather than
 * after it.
 *
 * The AI Engine is never contacted: ANALYSIS_PROVIDER is overridden with a fake,
 * so this suite has no network dependency and no dependency on Member 3's
 * service running.
 */
import { jest } from '@jest/globals';
import 'reflect-metadata';
import type { INestApplication } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../app.module.js';
import {
  ANALYSIS_PROVIDER,
  type AnalysisRequest,
  type IAnalysisProvider,
} from './interfaces/analysis-provider.interface.js';
import type { AnalysisResult } from './models/analysis-result.model.js';

/** The DTO's @MaxLength bound. One character over must be rejected. */
const MAX_CODE_LENGTH = 100000;

const FAKE_RESULT: AnalysisResult = {
  requestId: 'unused-sentinel',
  language: 'typescript',
  symbols: [],
  relationships: [],
  summary: 'fake result',
  confidence: { level: 'unknown' },
  evidence: [],
  analysedAt: '2026-01-01T00:00:00.000Z',
};

const analyzeCode = jest.fn(
  async (analysisRequest: AnalysisRequest): Promise<AnalysisResult> => ({
    ...FAKE_RESULT,
    requestId: analysisRequest.requestId,
  }),
);

const fakeProvider: IAnalysisProvider = { analyzeCode };

describe('AnalysisController (Phase 4 input validation)', () => {
  let app: INestApplication;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(ANALYSIS_PROVIDER)
      .useValue(fakeProvider)
      .compile();

    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    analyzeCode.mockClear();
  });

  describe('POST /analysis/code', () => {
    it('accepts a valid request and calls the provider exactly once', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: 'typescript', code: 'const x = 1;' });

      expect(response.status).toBe(201);
      expect(analyzeCode).toHaveBeenCalledTimes(1);
      expect(analyzeCode).toHaveBeenCalledWith(
        expect.objectContaining({
          language: 'typescript',
          code: 'const x = 1;',
        }),
      );
      expect(response.body).toMatchObject({ language: 'typescript' });
    });

    it('preserves optional properties that carry validation metadata', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({
          language: 'typescript',
          code: 'const x = 1;',
          filePath: 'src/index.ts',
          context: 'some context',
        });

      expect(response.status).toBe(201);
      expect(analyzeCode).toHaveBeenCalledTimes(1);
      expect(analyzeCode).toHaveBeenCalledWith(
        expect.objectContaining({
          filePath: 'src/index.ts',
          context: 'some context',
        }),
      );
    });

    it('rejects empty code without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: 'typescript', code: '' });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });

    it('rejects whitespace-only code without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: 'typescript', code: '   \t\n  ' });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });

    it('rejects code exceeding the maximum length without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({
          language: 'typescript',
          code: 'a'.repeat(MAX_CODE_LENGTH + 1),
        });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });

    it('accepts code exactly at the maximum length', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({
          language: 'typescript',
          code: 'a'.repeat(MAX_CODE_LENGTH),
        });

      expect(response.status).toBe(201);
      expect(analyzeCode).toHaveBeenCalledTimes(1);
    });

    it('rejects a missing language without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ code: 'const x = 1;' });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });

    it('rejects whitespace-only language without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: '   ', code: 'const x = 1;' });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });

    it('rejects an unknown property without calling the provider', async () => {
      const response = await request(app.getHttpServer())
        .post('/analysis/code')
        .send({ language: 'typescript', code: 'const x = 1;', foo: 'bar' });

      expect(response.status).toBe(400);
      expect(analyzeCode).not.toHaveBeenCalled();
    });
  });
});
