/**
 * Phase 6 inbound X-Request-Id validation.
 *
 * Echoing a client-supplied correlation ID is a genuine operational win: a
 * caller that already has an ID from its own gateway can hand us that same ID and
 * then correlate their logs with ours. It is also a genuine injection risk,
 * because the value is attacker-controlled and would otherwise be written into
 * a log line and reflected into a response header.
 *
 * The rule is a single allowlist pattern. A permitted ID is 1-128 characters of
 * ASCII letters, digits, dot, underscore, tilde and dash. That grammar
 * deliberately excludes:
 *
 *   - CR, LF and every other control character, so a value cannot forge a second
 *     log line or smuggle a header
 *   - whitespace, so a padded or space-injected value cannot slip through
 *   - ':' and every other delimiter, so the value cannot be reinterpreted as a
 *     header or URL component
 *   - anything non-ASCII
 *
 * Anything failing the pattern is replaced with a fresh UUID rather than
 * sanitized or repaired. Generating a new ID is always safe, whereas trying to
 * clean an arbitrary string risks preserving something an attacker chose.
 */
import { randomUUID } from 'crypto';

/** The inbound request header name, lower-cased as Node normalises headers. */
export const X_REQUEST_ID_HEADER = 'x-request-id';

/** Maximum accepted length of a client-supplied correlation ID. */
export const MAX_REQUEST_ID_LENGTH = 128;

/** The allowlist grammar a client-supplied correlation ID must satisfy. */
export const REQUEST_ID_PATTERN = /^[A-Za-z0-9._~-]{1,128}$/;

/**
 * Type guard for an acceptable correlation ID.
 *
 * Rejects anything that is not a string, so a repeated header arriving as an
 * array is refused rather than coerced.
 */
export function isValidRequestId(value: unknown): value is string {
  return typeof value === 'string' && REQUEST_ID_PATTERN.test(value);
}

/**
 * Reduces a raw header value to a single candidate string.
 *
 * Node collapses most repeated headers into a comma-joined string, and exposes
 * `set-cookie`-style headers as an array. A comma-joined value will not match
 * the allowlist and will be replaced downstream, which is the desired outcome;
 * an array is normalised here so the decision is made in one place.
 */
export function toHeaderCandidate(value: unknown): unknown {
  if (Array.isArray(value)) return value[0];
  return value;
}

/**
 * Resolves the correlation ID for a request.
 *
 * A valid supplied ID is honoured so a caller can correlate across services. Any
 * invalid or absent value yields a fresh UUID, so every request that reaches the
 * AI Engine integration has a usable, safe ID.
 */
export function resolveRequestId(supplied: unknown): string {
  return isValidRequestId(supplied) ? supplied : randomUUID();
}
