import { Test, type TestingModule } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { fileURLToPath } from 'url';
import { AppModule } from '../src/app.module.js';

const FIXTURE_ROOT = fileURLToPath(
  new URL('./fixtures/auth-project', import.meta.url),
);

describe('POST /repository/index (e2e)', () => {
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

  it('indexes a repository through the real AST adapter', async () => {
    const response = await request(app.getHttpServer())
      .post('/repository/index')
      .send({ repositoryPath: FIXTURE_ROOT })
      .expect(201);

    expect(response.body.stats.fileCount).toBeGreaterThanOrEqual(5);
    expect(response.body.stats.symbolCount).toBeGreaterThan(0);
    expect(response.body.stats.relationshipCount).toBeGreaterThan(0);
    expect(response.body.stats.chunkCount).toBeGreaterThan(0);
    expect(Array.isArray(response.body.files)).toBe(true);
    expect(Array.isArray(response.body.symbols)).toBe(true);
    expect(Array.isArray(response.body.relationships)).toBe(true);
    expect(Array.isArray(response.body.chunks)).toBe(true);
  });

  it('rejects a missing repositoryPath', async () => {
    await request(app.getHttpServer())
      .post('/repository/index')
      .send({})
      .expect(400);
  });

  it('returns 404 for a non-existent repository', async () => {
    await request(app.getHttpServer())
      .post('/repository/index')
      .send({ repositoryPath: 'Z:/definitely/not/here' })
      .expect(404);
  });
});

describe('GET /health (e2e)', () => {
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

  it('returns 200 with {"status":"ok"}', async () => {
    const response = await request(app.getHttpServer())
      .get('/health')
      .expect(200);
    expect(response.body).toEqual({ status: 'ok' });
  });
});
