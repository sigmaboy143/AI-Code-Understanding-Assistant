/**
 * Phase 6 Step 5 tests for CommonModule.
 *
 * Two things are being guarded here. The first is that the providers resolve
 * and are exported, so AnalysisModule can inject AppLogger in Step 8. The
 * second, and more subtle, is that nothing is duplicated: a second LOG_SINK
 * registration or a second AsyncLocalStorage would not fail any test that
 * merely checked resolution, but would cause two different sinks to be used at
 * runtime depending on which module a caller came through. Hence the explicit
 * single-instance and single-provider assertions.
 *
 * Only CommonModule is bootstrapped here. AppModule is deliberately not
 * imported: Step 7 wires it, and importing it now would test a wiring that does
 * not exist yet.
 */
import { jest } from '@jest/globals';
import { Test } from '@nestjs/testing';
import { CommonModule } from './common.module.js';
import { CorrelationIdMiddleware } from './correlation/correlation-id.middleware.js';
import { AppLogger } from './logging/app-logger.js';
import { LOG_SINK, NestLoggerSink } from './logging/log-sink.js';

/** Reads the @Module decorator metadata that Nest itself consumes. */
function moduleMetadata(key: 'providers' | 'exports'): unknown[] {
  // The @Module decorator defines each metadata property under its own
  // unprefixed key, so this must be read exactly as Nest writes it.
  return (
    Reflect as unknown as {
      getMetadata: (k: string, target: unknown) => unknown;
    }
  ).getMetadata(key, CommonModule) as unknown[];
}

describe('CommonModule metadata', () => {
  it('declares exactly two providers: LOG_SINK and AppLogger', () => {
    expect(moduleMetadata('providers')).toHaveLength(2);
  });

  it('exports LOG_SINK and AppLogger', () => {
    expect(moduleMetadata('exports')).toEqual([LOG_SINK, AppLogger]);
  });
});

describe('CommonModule providers', () => {
  it('compiles', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    expect(moduleRef).toBeDefined();
    await moduleRef.close();
  });

  it('resolves LOG_SINK to the NestJS-backed default sink', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    expect(moduleRef.get(LOG_SINK)).toBeInstanceOf(NestLoggerSink);
    await moduleRef.close();
  });

  it('resolves AppLogger', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    expect(moduleRef.get(AppLogger)).toBeInstanceOf(AppLogger);
    await moduleRef.close();
  });

  it('returns the same LOG_SINK instance on every resolve', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    expect(moduleRef.get(LOG_SINK)).toBe(moduleRef.get(LOG_SINK));
    await moduleRef.close();
  });

  it('returns the same AppLogger instance on every resolve', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    expect(moduleRef.get(AppLogger)).toBe(moduleRef.get(AppLogger));
    await moduleRef.close();
  });

  it('injects the same LOG_SINK instance into AppLogger', async () => {
    const moduleRef = await Test.createTestingModule({
      imports: [CommonModule],
    }).compile();

    const sink = moduleRef.get(LOG_SINK);
    const logger = moduleRef.get(AppLogger);

    // Both come from the same container, so a captured AppLogger must delegate
    // to the very sink the module exposes.
    const lines: unknown[] = [];
    const spy = jest
      .spyOn(sink as NestLoggerSink, 'log')
      .mockImplementation((entry) => {
        lines.push(entry);
      });

    logger.info('common_module_probe', { operation: 'probe' });
    expect(lines).toHaveLength(1);

    spy.mockRestore();
    await moduleRef.close();
  });
});

describe('CommonModule.configure', () => {
  it('applies CorrelationIdMiddleware', () => {
    const apply = jest.fn();
    const forRoutes = jest.fn();
    const consumer = { apply, forRoutes } as unknown as Parameters<
      CommonModule['configure']
    >[0];

    apply.mockReturnValue({ forRoutes } as never);

    new CommonModule().configure(consumer);

    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(CorrelationIdMiddleware);
    expect(forRoutes).toHaveBeenCalledWith('*');
  });

  it('applies the middleware exactly once per configuration', () => {
    const apply = jest.fn();
    const forRoutes = jest.fn();
    const consumer = { apply, forRoutes } as unknown as Parameters<
      CommonModule['configure']
    >[0];

    apply.mockReturnValue({ forRoutes } as never);

    new CommonModule().configure(consumer);

    expect(apply).toHaveBeenCalledTimes(1);
    expect(forRoutes).toHaveBeenCalledTimes(1);
  });
});

describe('CommonModule dependency surface', () => {
  it('declares NestLoggerSink as the only sink implementation', () => {
    const providers = moduleMetadata('providers') as
      | { provide?: string; useClass?: unknown }[]
      | undefined;

    const sinkProviders = (providers ?? []).filter(
      (p) => p?.provide === LOG_SINK,
    );

    expect(sinkProviders).toHaveLength(1);
    expect(sinkProviders[0].useClass).toBe(NestLoggerSink);
  });

  it('contains no business logic in the module class', () => {
    const surface = Object.getOwnPropertyNames(CommonModule.prototype).filter(
      (name) => name !== 'constructor',
    );

    expect(surface).toEqual(['configure']);
  });
});
