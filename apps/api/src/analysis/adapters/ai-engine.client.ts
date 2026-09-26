import { Inject, Injectable } from '@nestjs/common';
import type { AiEngineConfig } from '../config/ai-engine.config.js';
import { AI_ENGINE_CONFIG } from '../config/ai-engine.config.js';
import type { AiEngineRequestContract } from '../contracts/ai-engine-request.contract.js';
import type {
  AiEngineErrorEnvelope,
  AiEngineResponseContract,
} from '../contracts/ai-engine-response.contract.js';

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

  constructor(
    @Inject(AI_ENGINE_CONFIG)
    private readonly config: AiEngineConfig,
  ) {
    this.endpoint = `${config.baseUrl}/api/v1/code-understanding`;
  }

  async post(body: AiEngineRequestContract): Promise<AiEngineResponseContract> {
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
        throw new AiEngineClientError('timeout');
      }
      throw new AiEngineClientError(
        'network_error',
        err instanceof Error ? err.message : String(err),
      );
    }

    clearTimeout(timer);

    if (response.ok) {
      return response.json() as Promise<AiEngineResponseContract>;
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

    throw new AiEngineClientError(code, upstreamMessage);
  }
}
