/**
 * Phase 6 Step 2 tests for the log sink: injection, delegation and levels.
 *
 * The delegation assertions spy on the NestJS Logger prototype rather than
 * capturing stdout. That matters: stdout capture would pass even if the wrong
 * level or the wrong context were used, because both end up on the same stream.
 * Spying proves the sink forwards the level and the context faithfully.
 */
import { jest } from '@jest/globals';
import { Test } from '@nestjs/testing';
import { Logger } from '@nestjs/common';
import { LOG_SINK, NestLoggerSink, type LogEntry } from './log-sink.js';
import { AppLogger } from './app-logger.js';

/** Builds a complete entry so individual tests can override one field. */
function entry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    level: 'info',
    context: 'AiEngineClient',
    message: 'ai_engine_interaction',
    fields: {},
    ...overrides,
  };
}

describe('LOG_SINK token', () => {
  it('is a stable string token', () => {
    expect(LOG_SINK).toBe('LOG_SINK');
  });

  it('can be resolved by the Nest injector', async () => {
    const moduleRef = await Test.createTestingModule({
      providers: [{ provide: LOG_SINK, useClass: NestLoggerSink }],
    }).compile();

    expect(moduleRef.get(LOG_SINK)).toBeInstanceOf(NestLoggerSink);
    await moduleRef.close();
  });

  it('can be replaced by a test fake', async () => {
    const entries: LogEntry[] = [];
    const fake = { log: (e: LogEntry) => entries.push(e) };

    const moduleRef = await Test.createTestingModule({
      providers: [{ provide: LOG_SINK, useValue: fake }],
    }).compile();

    const sink = moduleRef.get<{ log: (e: LogEntry) => void }>(LOG_SINK);
    sink.log(entry({ message: 'from_fake' }));

    expect(moduleRef.get(LOG_SINK)).toBe(fake);
    expect(entries).toHaveLength(1);
    expect(entries[0].message).toBe('from_fake');
    await moduleRef.close();
  });
});

describe('NestLoggerSink', () => {
  let sink: NestLoggerSink;
  let logSpy: ReturnType<typeof jest.spyOn>;
  let warnSpy: ReturnType<typeof jest.spyOn>;
  let errorSpy: ReturnType<typeof jest.spyOn>;

  beforeEach(() => {
    sink = new NestLoggerSink();
    logSpy = jest.spyOn(Logger.prototype, 'log').mockImplementation(() => {});
    warnSpy = jest.spyOn(Logger.prototype, 'warn').mockImplementation(() => {});
    errorSpy = jest.spyOn(Logger.prototype, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('delegates info to Nest Logger.log', () => {
    sink.log(entry({ level: 'info' }));

    expect(logSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('delegates warn to Nest Logger.warn', () => {
    sink.log(entry({ level: 'warn' }));

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(logSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('delegates error to Nest Logger.error', () => {
    sink.log(entry({ level: 'error' }));

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(logSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('forwards the context tag to Nest Logger', () => {
    sink.log(entry({ context: 'AiEngineClient' }));

    expect(logSpy.mock.calls[0][1]).toBe('AiEngineClient');
  });

  it('renders sanitized fields alongside the message', () => {
    sink.log(
      entry({
        message: 'ai_engine_interaction',
        fields: { operation: 'post', status: 200, durationMs: 12.5 },
      }),
    );

    expect(logSpy.mock.calls[0][0]).toBe(
      'ai_engine_interaction {"operation":"post","status":200,"durationMs":12.5}',
    );
  });

  it('emits exactly one line per entry', () => {
    sink.log(entry());
    sink.log(entry({ level: 'warn' }));
    sink.log(entry({ level: 'error' }));

    expect(logSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledTimes(1);
  });
});

describe('AppLogger', () => {
  let entries: LogEntry[];
  let sink: { log: (e: LogEntry) => void };
  let logger: AppLogger;

  beforeEach(() => {
    entries = [];
    sink = { log: (e: LogEntry) => entries.push(e) };
    logger = new AppLogger(sink).withContext('AiEngineClient');
  });

  it('defaults the context tag to App', () => {
    expect(new AppLogger(sink).getContext()).toBe('App');
  });

  it('preserves the supplied context tag', () => {
    expect(logger.getContext()).toBe('AiEngineClient');
  });

  it('attaches its context to every entry', () => {
    logger.info('a');
    logger.warn('b');
    logger.error('c');

    expect(entries.map((e) => e.context)).toEqual([
      'AiEngineClient',
      'AiEngineClient',
      'AiEngineClient',
    ]);
  });

  it('preserves info, warn and error levels', () => {
    logger.info('a');
    logger.warn('b');
    logger.error('c');

    expect(entries.map((e) => e.level)).toEqual(['info', 'warn', 'error']);
  });

  it('lets allowed structured fields reach the sink', () => {
    logger.info('ai_engine_interaction', {
      operation: 'post',
      path: '/api/v1/code-understanding',
      status: 200,
      durationMs: 12.5,
      code: 'timeout',
      requestId: 'req-1',
      outcome: 'success',
    });

    expect(entries[0].fields).toEqual({
      operation: 'post',
      path: '/api/v1/code-understanding',
      status: 200,
      durationMs: 12.5,
      code: 'timeout',
      requestId: 'req-1',
      outcome: 'success',
    });
  });

  it('redacts disallowed fields before they reach the sink', () => {
    logger.info('ai_engine_interaction', {
      operation: 'post',
      language: 'typescript',
      filePath: 'src/index.ts',
    });

    expect(entries[0].fields).toEqual({ operation: 'post' });
  });

  it('never lets source_code reach the sink', () => {
    logger.info('ai_engine_interaction', {
      operation: 'post',
      source_code: 'const apiKey = "sk-live-DO-NOT-LOG";',
    });

    const serialized = JSON.stringify(entries[0]);
    expect(entries[0].fields).not.toHaveProperty('source_code');
    expect(serialized).not.toContain('sk-live-DO-NOT-LOG');
  });

  it('never lets a request or response body reach the sink', () => {
    logger.warn('ai_engine_interaction', {
      operation: 'post',
      body: { source_code: 'private' },
      responseBody: '{"summary":"private"}',
    });

    expect(entries[0].fields).toEqual({ operation: 'post' });
  });

  it('never lets source code reach the sink through the code field', () => {
    logger.error('ai_engine_interaction', {
      code: 'const x = 1; // not a code',
    });

    expect(entries[0].fields).not.toHaveProperty('code');
  });

  it('emits exactly one entry per call', () => {
    logger.info('a');
    expect(entries).toHaveLength(1);
  });

  it('tolerates being called with no fields at all', () => {
    logger.info('no_fields');

    expect(entries[0].fields).toEqual({});
  });

  it('derives a differently tagged logger over the same sink', () => {
    const tagged = logger.withContext('HealthService');

    expect(tagged).not.toBe(logger);
    expect(tagged.getContext()).toBe('HealthService');

    tagged.info('from_tagged');
    expect(entries[0].context).toBe('HealthService');
  });

  it('exposes no public path to the raw sink', () => {
    // Guards against a future "just log this raw" escape hatch appearing on the
    // public surface, which would bypass the allowlist entirely.
    const surface = Object.getOwnPropertyNames(AppLogger.prototype).filter(
      (name) => name !== 'constructor',
    );

    expect(surface.sort()).toEqual([
      'emit',
      'error',
      'getContext',
      'info',
      'warn',
      'withContext',
    ]);
  });

  it('resolves LOG_SINK through the Nest injector', async () => {
    // AppLogger is registered as a plain class provider, not via useFactory.
    // That is deliberate: a factory would hide an unresolvable constructor
    // parameter, and AppLogger must be injectable by its class token wherever
    // it is provided.
    const moduleRef = await Test.createTestingModule({
      providers: [{ provide: LOG_SINK, useClass: NestLoggerSink }, AppLogger],
    }).compile();

    expect(moduleRef.get(AppLogger)).toBeInstanceOf(AppLogger);
    expect(moduleRef.get(AppLogger).getContext()).toBe('App');
    await moduleRef.close();
  });
});
