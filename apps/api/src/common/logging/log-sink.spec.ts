/**
 * Phase 6 Step 2 tests for the LogSink contract itself.
 *
 * Separated from app-logger.spec.ts because the two answer different questions:
 * this file asks "is the sink contract coherent and injectable", while the other
 * asks "does anything unsafe reach it". Keeping them apart means a failure
 * points at the right layer.
 */
import { jest } from '@jest/globals';
import { Test } from '@nestjs/testing';
import { Logger } from '@nestjs/common';
import { LOG_SINK, NestLoggerSink, type LogEntry } from './log-sink.js';
import { formatLogMessage } from './redact.js';

describe('LogSink contract', () => {
  it('is satisfied by NestLoggerSink', () => {
    const sink: { log(entry: LogEntry): void } = new NestLoggerSink();

    expect(typeof sink.log).toBe('function');
  });

  it('is satisfied by a minimal test fake', () => {
    const captured: LogEntry[] = [];
    const sink = { log: (e: LogEntry) => captured.push(e) };

    sink.log({
      level: 'info',
      context: 'Test',
      message: 'hello',
      fields: { operation: 'post' },
    });

    expect(captured).toHaveLength(1);
    expect(captured[0].fields.operation).toBe('post');
  });
});

describe('NestLoggerSink defaults to info for an unrecognised level', () => {
  it('routes an unknown level to Logger.log rather than dropping it', () => {
    const sink = new NestLoggerSink();
    const logSpy = jest
      .spyOn(Logger.prototype, 'log')
      .mockImplementation(() => {});

    sink.log({
      level: 'debug' as unknown as LogEntry['level'],
      context: 'Test',
      message: 'unknown_level',
      fields: {},
    });

    expect(logSpy).toHaveBeenCalledTimes(1);
    jest.restoreAllMocks();
  });
});

describe('message rendering', () => {
  it('appends a JSON field object to the constant message', () => {
    expect(
      formatLogMessage('ai_engine_interaction', { operation: 'post' }),
    ).toBe('ai_engine_interaction {"operation":"post"}');
  });

  it('omits the field object entirely when there are no fields', () => {
    expect(formatLogMessage('ai_engine_interaction', {})).toBe(
      'ai_engine_interaction',
    );
  });

  it('never produces a multi-line string from sanitized fields', () => {
    const line = formatLogMessage('ai_engine_interaction', {
      operation: 'post',
      requestId: 'req-1',
    });

    expect(line).not.toContain('\n');
    expect(line).not.toContain('\r');
  });
});

describe('LOG_SINK provider registration shape', () => {
  it('supports useValue override for deterministic assertions', async () => {
    const seen: LogEntry[] = [];

    const moduleRef = await Test.createTestingModule({
      providers: [{ provide: LOG_SINK, useValue: { log: (e: LogEntry) => seen.push(e) } }],
    }).compile();

    moduleRef.get<{ log: (e: LogEntry) => void }>(LOG_SINK).log({
      level: 'error',
      context: 'AiEngineClient',
      message: 'ai_engine_interaction',
      fields: { code: 'timeout' },
    });

    expect(seen).toHaveLength(1);
    expect(seen[0].level).toBe('error');
    expect(seen[0].fields.code).toBe('timeout');
    await moduleRef.close();
  });

  it('supports useClass registration of the default sink', async () => {
    const moduleRef = await Test.createTestingModule({
      providers: [{ provide: LOG_SINK, useClass: NestLoggerSink }],
    }).compile();

    expect(moduleRef.get(LOG_SINK)).toBeInstanceOf(NestLoggerSink);
    await moduleRef.close();
  });
});
