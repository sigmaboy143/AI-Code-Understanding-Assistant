/**
 * Injection token for the AI Engine configuration.
 * Register via a factory provider in AnalysisModule so tests can
 * override it with { provide: AI_ENGINE_CONFIG, useValue: {...} }.
 */
export const AI_ENGINE_CONFIG = 'AI_ENGINE_CONFIG';

export interface AiEngineConfig {
  /**
   * Base URL of the AI Engine service.
   * Configured via AI_ENGINE_BASE_URL environment variable.
   * Defaults to http://127.0.0.1:8000 for local development.
   *
   * This is the NestJS adapter's own variable — do not confuse with
   * the AI Engine's internal HOST/PORT variables.
   */
  baseUrl: string;

  /**
   * Request timeout in milliseconds for calls from NestJS to the AI Engine.
   * Configured via AI_ENGINE_TIMEOUT_MS environment variable.
   * Defaults to 60000 (60 seconds).
   *
   * This is the NestJS adapter's timeout — do not confuse with
   * the AI Engine's internal REQUEST_TIMEOUT variable.
   *
   * The default is derived from measured behaviour rather than picked freely.
   * A real NestJS -> AI Engine -> Ollama/llama3 analysis completed in 34.3s, so
   * the previous 10000ms default could not have succeeded against a live
   * provider, and any value under 34.3s will fail for slow-but-valid requests.
   * 60s matches the AI Engine's own REQUEST_TIMEOUT budget, so this remains an
   * honest upper bound on the round trip rather than an invented number. An
   * AI Engine 504 and a local abort both surface as GatewayTimeoutException, so
   * the boundary stays consistent for callers even when it is crossed.
   *
   * Note that this budget is only usable if callers can wait for it. A
   * client-side timeout below this value will give up first and report a
   * failure while the backend is still legitimately working.
   */
  timeoutMs: number;
}

/**
 * Default request timeout in milliseconds, in the absence of
 * AI_ENGINE_TIMEOUT_MS. See AiEngineConfig.timeoutMs for why this is 60s.
 */
const DEFAULT_TIMEOUT_MS = 60_000;

/**
 * Factory function registered as a NestJS useFactory provider.
 * Reads environment variables once at module init.
 */
export function createAiEngineConfig(): AiEngineConfig {
  return {
    baseUrl: process.env['AI_ENGINE_BASE_URL'] ?? 'http://127.0.0.1:8000',
    timeoutMs: Number(process.env['AI_ENGINE_TIMEOUT_MS'] ?? DEFAULT_TIMEOUT_MS),
  };
}
