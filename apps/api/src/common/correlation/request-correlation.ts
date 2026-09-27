/**
 * Phase 6 request correlation: one ID per request, available everywhere.
 *
 * The problem this solves is that `AnalysisService` already generated a
 * `requestId` and returned it to the client, but that ID appeared in no log,
 * because no logs existed. Simply adding logging would therefore still leave
 * the client holding a number an operator cannot search for. Threading an ID
 * through every method signature to fix that would touch AnalysisService,
 * AnalysisController and the provider interface, which AGENTS.md explicitly
 * asks us not to disturb.
 *
 * AsyncLocalStorage avoids both problems. The middleware binds an ID once for
 * the lifetime of the request; anything running inside that request's async
 * context can read it with getCorrelationId() without any parameter being
 * threaded through. NestJS instantiates the store once at module scope, so the
 * context is correct for every request without any provider wiring and without
 * any global mutable state being shared between requests.
 *
 * Isolation is the property that makes this safe: because each request calls
 * run() on its own context, two concurrent requests cannot observe each other's
 * ID, no matter how their promises interleave.
 */
import { AsyncLocalStorage } from 'async_hooks';

/** The per-request correlation context. */
export interface CorrelationContext {
  readonly requestId: string;
}

/**
 * Module-scoped store. Created once when the module is first imported.
 *
 * Deliberately not a provider: correlation must work in any context, including
 * code that is constructed outside the Nest injector, and a module-scoped
 * AsyncLocalStorage is what guarantees that.
 */
const correlationStorage = new AsyncLocalStorage<CorrelationContext>();

/**
 * Runs `fn` with `requestId` bound as the correlation context.
 *
 * The binding applies to `fn` and to every async operation it starts, however
 * deeply nested. The return value is passed through unchanged, so this is safe
 * to wrap an async request handler directly.
 */
export function runWithCorrelation<T>(
  requestId: string,
  fn: () => T,
): T {
  return correlationStorage.run({ requestId }, fn);
}

/**
 * Returns the current request's correlation ID, or undefined outside any
 * correlation context.
 *
 * The undefined case is a normal, expected outcome rather than an error: it
 * occurs for startup work, scheduled jobs, and any code exercised directly by a
 * unit test. Callers are expected to fall back, which is exactly what
 * AnalysisService does with `getCorrelationId() ?? randomUUID()`.
 */
export function getCorrelationId(): string | undefined {
  return correlationStorage.getStore()?.requestId;
}
