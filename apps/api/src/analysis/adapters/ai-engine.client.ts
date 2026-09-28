import { Inject, Injectable } from '@nestjs/common';
import { performance } from 'perf_hooks';
import { AppLogger } from '../../common/logging/app-logger.js';
import { getCorrelationId } from '../../common/correlation/request-correlation.js';
import type { AiEngineConfig } from '../config/ai-engine.config.js';
import { AI_ENGINE_CONFIG } from '../config/ai-engine.config.js';
import type { AiEngineRequestContract } from '../contracts/ai-engine-request.contract.js';
import type {
  AiEngineErrorEnvelope,
  AiEngineResponseContract,
} from '../contracts/ai-engine-response.contract.js';

// ---------------------------------------------------------------------------
// Paths
//
// Declared once and used for BOTH endpoint construction and the `path` log
// field, so a URL and its logged path can never drift apart. The resulting URLs
// are byte-identical to the Phase 3 literals; the existing endpoint assertions
// in the spec are what prove it.

const ANALYSIS_PATH = '/api/v1/code-understanding';
const READINESS_PATH = '/ready';

/** Constant message for every AI Engine interaction log line. */
const INTERACTION_MESSAGE = 'ai_engine_interaction';

// ---------------------------------------------------------------------------
// Typed error

export type AiEngineClientErrorCode =
  | 'validation_error' // 422
  | 'provider_unavailable' // 503
  | 'provider_timeout' // 504
  | 'provider_error' // 502
  | 'internal_error' // 500
  | 'network_error' // fetch threw (non-abort)
  | 'timeout'; // AbortController fired

export class AiEngineClientError extends Error {
  constructor(
    public readonly code: AiEngineClientErrorCode,
    /** Upstream message from the AI Engine error envelope — for operator logs only. */
    public readonly upstreamMessage?: string,
  ) {
    super(`AiEngineClientError [${code}]${upstreamMessage ? `: ${upstreamMessage}` : ''}`);
    this.name = 'AiEngineClientError';
  }
}

// ---------------------------------------------------------------------------
// HTTP status → error code

const STATUS_TO_CODE: Readonly<Record<number, AiEngineClientErrorCode>> = {
  422: 'validation_error',
  503: 'provider_unavailable',
  504: 'provider_timeout',
  502: 'provider_error',
  500: 'internal_error',
};

// ---------------------------------------------------------------------------

@Injectable()
export class AiEngineClient {
  private readonly endpoint: string;
  private readonly readinessEndpoint: string;
  private readonly logger: AppLogger;

  constructor(
    @Inject(AI_ENGINE_CONFIG)
    private readonly config: AiEngineConfig,
    logger: AppLogger,
  ) {
    this.endpoint = `${config.baseUrl}${ANALYSIS_PATH}`;
    this.readinessEndpoint = `${config.baseUrl}${READINESS_PATH}`;
    this.logger = logger.withContext('AiEngineClient');
  }

  async post(body: AiEngineRequestContract): Promise<AiEngineResponseContract> {
    const startedAt = performance.now();
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(),
      this.config.timeoutMs,
    );

    let response: Response;

    try {
      response = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timer);
      if (
        typeof err === 'object' &&
        err !== null &&
        'name' in err &&
        (err as { name?: unknown }).name === 'AbortError'
      ) {
        this.logInteraction('warn', {
          operation: 'post',
          path: ANALYSIS_PATH,
          status: null,
          durationMs: this.elapsedSince(startedAt),
          code: 'timeout',
          outcome: 'error',
        });
        throw new AiEngineClientError('timeout');
      }
      this.logInteraction('error', {
        operation: 'post',
        path: ANALYSIS_PATH,
        status: null,
        durationMs: this.elapsedSince(startedAt),
        code: 'network_error',
        outcome: 'error',
      });
      throw new AiEngineClientError(
        'network_error',
        err instanceof Error ? err.message : String(err),
      );
    }

    clearTimeout(timer);

    if (response.ok) {
      const parsed = (await response.json()) as AiEngineResponseContract;
      this.logInteraction('info', {
        operation: 'post',
        path: ANALYSIS_PATH,
        status: response.status,
        durationMs: this.elapsedSince(startedAt),
        code: 'success',
        outcome: 'success',
      });
      return parsed;
    }

    // Attempt to parse the AI Engine error envelope
    let upstreamMessage: string | undefined;
    try {
      const envelope = (await response.json()) as AiEngineErrorEnvelope;
      upstreamMessage = envelope?.error?.message;
    } catch {
      // Response body was not parseable — proceed with status-only error
    }

    const code: AiEngineClientErrorCode =
      STATUS_TO_CODE[response.status] ?? 'internal_error';

    this.logInteraction(
      typeof response.status === 'number' && response.status >= 500
        ? 'error'
        : 'warn',
      {
        operation: 'post',
        path: ANALYSIS_PATH,
        status: response.status,
        durationMs: this.elapsedSince(startedAt),
        code,
        outcome: 'error',
      },
    );

    throw new AiEngineClientError(code, upstreamMessage);
  }

  /**
   * Phase 5 readiness probe.
   *
   * Additive capability for the NestJS /ready endpoint. Does not touch the
   * Phase 3 analysis path: `post()` and `this.endpoint` are unchanged.
   *
   * Targets the AI Engine's documented readiness endpoint (GET /ready, see
   * AGENTS.md "AI Engine Contract") — not its liveness endpoint — so backend
   * readiness reflects upstream readiness rather than mere process liveness.
   *
   * The response body is deliberately NOT parsed. Readiness only needs to know
   * whether the upstream answered successfully, so any 2xx resolves and any
   * non-2xx throws with the same AiEngineClientError codes the analysis path
   * already uses. Reusing config.timeoutMs and the AbortController pattern
   * keeps a single timeout policy for all AI Engine traffic, and guarantees a
   * probe terminates (as 'timeout') instead of hanging.
   *
   * @throws {AiEngineClientError} 'timeout' | 'network_error' | an existing
   *   mapped code for a non-2xx response. No upstream body is captured, so no
   *   upstream text is retained for callers to leak.
   */
  async checkReadiness(): Promise<void> {
    const startedAt = performance.now();
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(),
      this.config.timeoutMs,
    );

    let response: Response;

    try {
      response = await fetch(this.readinessEndpoint, {
        method: 'GET',
        signal: controller.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timer);
      if (
        typeof err === 'object' &&
        err !== null &&
        'name' in err &&
        (err as { name?: unknown }).name === 'AbortError'
      ) {
        this.logInteraction('warn', {
          operation: 'checkReadiness',
          path: READINESS_PATH,
          status: null,
          durationMs: this.elapsedSince(startedAt),
          code: 'timeout',
          outcome: 'error',
        });
        throw new AiEngineClientError('timeout');
      }
      this.logInteraction('error', {
        operation: 'checkReadiness',
        path: READINESS_PATH,
        status: null,
        durationMs: this.elapsedSince(startedAt),
        code: 'network_error',
        outcome: 'error',
      });
      throw new AiEngineClientError(
        'network_error',
        err instanceof Error ? err.message : String(err),
      );
    }

    clearTimeout(timer);

    if (response.ok) {
      this.logInteraction('info', {
        operation: 'checkReadiness',
        path: READINESS_PATH,
        status: response.status,
        durationMs: this.elapsedSince(startedAt),
        code: 'success',
        outcome: 'success',
      });
      return;
    }

    // Status-only: the body is intentionally not read.
    const code: AiEngineClientErrorCode =
      STATUS_TO_CODE[response.status] ?? 'internal_error';

    this.logInteraction(
      typeof response.status === 'number' && response.status >= 500
        ? 'error'
        : 'warn',
      {
        operation: 'checkReadiness',
        path: READINESS_PATH,
        status: response.status,
        durationMs: this.elapsedSince(startedAt),
        code,
        outcome: 'error',
      },
    );

    throw new AiEngineClientError(code);
  }

  // -------------------------------------------------------------------------
  // Phase 6 observability
  //
  // Every AI Engine interaction produces exactly one log entry, emitted from
  // exactly one of the four mutually exclusive exit paths above. The single
  // emit helper below is the only writer, so double-logging is structurally
  // impossible rather than merely avoided.
  //
  // Only the allowlisted structured fields are supplied. In particular the
  // upstream error message is NOT logged: it is arbitrary text from another
  // service and the approved allowlist has no field for it. `code` carries the
  // controlled AiEngineClient outcome token, which is what an operator needs to
  // triage a failure. Adding a sanitized upstream message would be a separate,
  // explicitly reviewed security change.
  //
  // The request ID is read from the correlation context and is undefined when
  // the client is exercised directly in a unit test. No second ID is invented
  // here: the middleware owns ID creation.

  private elapsedSince(startedAt: number): number {
    const elapsed = performance.now() - startedAt;
    // Guarantees the logged duration is always a finite, non-negative number,
    // including under fake timers where performance.now may not advance.
    return Number.isFinite(elapsed) && elapsed > 0 ? elapsed : 0;
  }

  private logInteraction(
    level: 'info' | 'warn' | 'error',
    fields: {
      operation: string;
      path: string;
      status: number | null;
      durationMs: number;
      code: string;
      outcome: string;
    },
  ): void {
    const payload = {
      operation: fields.operation,
      path: fields.path,
      // undefined rather than null: the redactor drops both, and a missing
      // status correctly signals that no HTTP response was ever received.
      status: fields.status ?? undefined,
      durationMs: fields.durationMs,
      code: fields.code,
      outcome: fields.outcome,
      requestId: getCorrelationId(),
    };

    if (level === 'warn') {
      this.logger.warn(INTERACTION_MESSAGE, payload);
    } else if (level === 'error') {
      this.logger.error(INTERACTION_MESSAGE, payload);
    } else {
      this.logger.info(INTERACTION_MESSAGE, payload);
    }
  }
}
