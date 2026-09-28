/**
 * Phase 6 correlation-ID middleware.
 *
 * Binds exactly one correlation ID per request and makes it available to
 * everything downstream, without any parameter threading.
 *
 * Three properties are load-bearing and each is asserted in the spec:
 *
 * 1. The response header is set BEFORE next() is invoked. Nest/Express run
 *    middleware ahead of pipes, so setting the header first means the ID is
 *    still present on a response that the Phase 4 ValidationPipe rejects with a
 *    400. Setting it after next() would lose it on exactly the requests where a
 *    caller most wants to correlate a rejection.
 *
 * 2. The ID is sanitized or replaced, never trusted. Validation is delegated to
 *    x-request-id.ts, so a CRLF header-injection attempt is discarded in favour
 *    of a generated UUID.
 *
 * 3. The middleware performs NO logging. It runs for every request in the
 *    application, including requests that never touch the AI Engine, and the
 *    Phase 6 invariant is one AI Engine interaction = one log entry. Logging
 *    here would break that invariant for readiness probes and would add a log
 *    line for unrelated endpoints. The only observable effects of this
 *    middleware are the correlation context and the response header.
 *
 * It likewise does not read or write request or response bodies.
 */
import { Injectable, type NestMiddleware } from '@nestjs/common';
import { runWithCorrelation } from './request-correlation.js';
import {
  X_REQUEST_ID_HEADER,
  resolveRequestId,
  toHeaderCandidate,
} from './x-request-id.js';

/** Response header carrying the correlation ID back to the caller. */
export const X_REQUEST_ID_RESPONSE_HEADER = 'X-Request-Id';

/**
 * Minimal structural view of the inbound request.
 *
 * Declared structurally rather than importing from express so that no HTTP
 * framework type becomes a dependency of this file. Only the headers bag is
 * read; the body is never touched.
 */
interface InboundRequest {
  readonly headers?: Readonly<Record<string, unknown>>;
}

/** Minimal structural view of the outbound response. */
interface OutboundResponse {
  setHeader(name: string, value: string): void;
}

@Injectable()
export class CorrelationIdMiddleware implements NestMiddleware {
  use(
    request: InboundRequest,
    response: OutboundResponse,
    next: () => void,
  ): void {
    const supplied = toHeaderCandidate(
      request.headers?.[X_REQUEST_ID_HEADER],
    );
    const requestId = resolveRequestId(supplied);

    // Set before next(): this is what survives a downstream 400.
    response.setHeader(X_REQUEST_ID_RESPONSE_HEADER, requestId);

    runWithCorrelation(requestId, next);
  }
}
