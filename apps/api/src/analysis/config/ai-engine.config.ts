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
   * Defaults to 10000 (10 seconds).
   *
   * This is the NestJS adapter's timeout — do not confuse with
   * the AI Engine's internal REQUEST_TIMEOUT variable.
   */
  timeoutMs: number;
}

/**
 * Factory function registered as a NestJS useFactory provider.
 * Reads environment variables once at module init.
 */
export function createAiEngineConfig(): AiEngineConfig {
  return {
    baseUrl: process.env['AI_ENGINE_BASE_URL'] ?? 'http://127.0.0.1:8000',
    timeoutMs: Number(process.env['AI_ENGINE_TIMEOUT_MS'] ?? 10_000),
  };
}
