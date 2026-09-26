import { HttpException, HttpStatus, Injectable } from '@nestjs/common';
import { AiEngineClient } from '../analysis/adapters/ai-engine.client.js';

/**
 * Public response contracts for the operational endpoints.
 *
 * These are deliberately narrow. Health and readiness are typically exposed to
 * load balancers, container orchestrators, and sometimes the public internet,
 * so the payloads carry a status word and nothing else — no version, no uptime,
 * no dependency URLs, no provider identity.
 */

export interface LivenessStatus {
  status: 'ok';
}

export interface ReadinessStatus {
  status: 'ready';
  aiEngine: 'ok';
}

export interface NotReadyStatus {
  status: 'not_ready';
  aiEngine: 'unavailable';
}

/**
 * Phase 5 health/readiness service.
 *
 * Liveness is a purely local, zero-I/O check: it reports that this NestJS
 * process is running and initialised, and must keep answering 200 even when
 * the AI Engine is completely unreachable. That independence is what allows an
 * orchestrator to distinguish "restart me" from "my dependency is down".
 *
 * Readiness is the dependency check. It asks the AI Engine's documented
 * readiness endpoint (GET /ready) whether AI-powered requests can be served,
 * and normalises every possible failure into a single 503 response.
 */
@Injectable()
export class HealthService {
  constructor(private readonly aiEngineClient: AiEngineClient) {}

  /**
   * Liveness check. Performs no network I/O and never calls the AI Engine —
   * it must not depend on any external service by definition.
   */
  liveness(): LivenessStatus {
    return { status: 'ok' };
  }

  /**
   * Readiness check against the AI Engine.
   *
   * Every failure mode of the probe — upstream non-2xx, connection refused,
   * timeout, or any unexpected error — collapses into one HttpException whose
   * body is exactly { status, aiEngine }. Nothing derived from the upstream
   * error (message, URL, port, or stack) is ever placed in the response, so
   * the endpoint is safe to expose publicly.
   *
   * No retry, backoff, or circuit breaking: a probe should reflect current
   * state, not accumulate state. Those belong to a later resilience phase.
   *
   * @throws {HttpException} 503 with a fixed public body when the AI Engine is
   *   not ready.
   */
  async readiness(): Promise<ReadinessStatus> {
    try {
      await this.aiEngineClient.checkReadiness();
    } catch {
      // The upstream error is deliberately discarded. It may contain the AI
      // Engine URL or transport-level text, neither of which may be exposed.
      throw new HttpException(
        {
          status: 'not_ready',
          aiEngine: 'unavailable',
        } satisfies NotReadyStatus,
        HttpStatus.SERVICE_UNAVAILABLE,
      );
    }

    return {
      status: 'ready',
      aiEngine: 'ok',
    };
  }
}
