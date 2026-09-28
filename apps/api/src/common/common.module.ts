/**
 * Phase 6 common infrastructure module.
 *
 * Owns the two cross-cutting concerns introduced by this phase and nothing
 * else. It contains no business logic: it exists so that `AppModule` does not
 * grow logging and middleware wiring, and so that any module needing to log can
 * import one place rather than redefining providers.
 *
 * Responsibilities, and nothing more:
 *
 *   1. Provide and export LOG_SINK and AppLogger exactly once. NestJS caches
 *      module instances by reference, so a module imported by several others
 *      still yields a single LOG_SINK and a single AppLogger. This is why the
 *      token is defined in log-sink.ts and re-exported here rather than being
 *      registered a second time.
 *
 *   2. Register CorrelationIdMiddleware for every route via configure(). It is
 *      applied to '*' because a correlation ID is useful on every request,
 *      including ones that never reach the AI Engine, and because the header
 *      must also be present on responses rejected by the global ValidationPipe.
 *
 * Deliberately NOT here:
 *
 *   - No second AsyncLocalStorage. The store is created once at module scope in
 *     request-correlation.ts and reused; creating another would silently split
 *     the correlation context in two.
 *   - No second logger implementation. NestLoggerSink is the only sink, and the
 *     default AppLogger context stays the generic 'App' so components label
 *     their own lines via withContext().
 *   - No LOG_SINK provider anywhere else. AnalysisModule imports this module to
 *     obtain AppLogger; it must never register its own sink.
 */
import { Module, type MiddlewareConsumer, type NestModule } from '@nestjs/common';
import { CorrelationIdMiddleware } from './correlation/correlation-id.middleware.js';
import { AppLogger } from './logging/app-logger.js';
import { LOG_SINK, NestLoggerSink } from './logging/log-sink.js';

@Module({
  providers: [
    {
      provide: LOG_SINK,
      useClass: NestLoggerSink,
    },
    AppLogger,
  ],
  exports: [LOG_SINK, AppLogger],
})
export class CommonModule implements NestModule {
  configure(consumer: MiddlewareConsumer): void {
    consumer.apply(CorrelationIdMiddleware).forRoutes('*');
  }
}
