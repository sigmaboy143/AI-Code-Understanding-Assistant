/**
 * Phase 6 security boundary for structured logging.
 *
 * THE ALLOWLIST IS THE SECURITY BOUNDARY. This file deliberately contains no
 * denylist. A denylist enumerates what must be removed, which means anything an
 * attacker or a future contributor has not yet thought of passes through
 * silently. An allowlist inverts that: a field is logged only if it appears in
 * ALLOWED_LOG_FIELDS *and* its value survives a strict type/format check.
 * Everything else is unreachable by construction rather than by vigilance.
 *
 * Why this is a hard boundary rather than a formatting nicety: the NestJS
 * backend forwards user-supplied source code to the AI Engine. If any of that
 * text could reach a log line it would land in log storage, log shipping, and
 * every developer's terminal, escaping the lifetime of the request. The
 * consequences of that leak are far worse than the consequences of a missing
 * log field, so the default here is always to drop.
 *
 * What the allowlist permits, and nothing else:
 *
 *   operation   a code-level constant such as 'post' or 'checkReadiness'
 *   path        the request path, with credentials and query string removed
 *   status      the HTTP status code
 *   durationMs  a non-negative elapsed time
 *   code        a controlled outcome code such as 'timeout' or 'network_error'
 *   requestId   the bounded, validated correlation ID
 *   outcome     a controlled result token such as 'success' or 'failure'
 *
 * The `code` field deserves a specific warning. In a Phase 6 log line, `code`
 * means ONLY the controlled AiEngineClient error/outcome code. It must never
 * carry source code, a request body, a response body, free-text context, a
 * question, or any other arbitrary user-controlled content. The format check
 * below enforces that structurally: a code is a short lowercase snake_case
 * token, so no sentence, path, or multi-line payload can satisfy it.
 *
 * Log injection: every value is stripped of control characters and then
 * format-checked, and the rendered message is built from a constant template
 * plus sanitized fields. A CR or LF in user data therefore cannot terminate a
 * line and forge a second log entry.
 */

/** Log levels the sink understands. */
export type LogLevel = 'info' | 'warn' | 'error';

/**
 * The complete set of field names permitted in a structured log entry.
 *
 * This is the security boundary. A key absent from this list is never read from
 * the input object, so it cannot be forwarded under any circumstance.
 */
export const ALLOWED_LOG_FIELDS = [
  'operation',
  'path',
  'status',
  'durationMs',
  'code',
  'requestId',
  'outcome',
] as const;

/** Union of the permitted field names. */
export type AllowedLogField = (typeof ALLOWED_LOG_FIELDS)[number];

/**
 * A fully sanitized log field set. Every property is optional because a caller
 * may legitimately report only some of them, and because an invalid value is
 * dropped rather than replaced with attacker-influenced text.
 */
export interface StructuredLogFields {
  operation?: string;
  path?: string;
  status?: number;
  durationMs?: number;
  code?: string;
  requestId?: string;
  outcome?: string;
}

/** Unvalidated input accepted by the sanitizer. */
export type UntrustedLogFields = Readonly<Record<string, unknown>>;

/** Placeholder emitted when a value is structurally present but unsafe. */
export const REDACTED = '[REDACTED]';

// ---------------------------------------------------------------------------
// Format rules
// ---------------------------------------------------------------------------

/**
 * A code-level identifier: a short alphanumeric/dot/dash/underscore token.
 * Case is permitted so 'checkReadiness' is a valid `operation`.
 */
const OPERATION_PATTERN = /^[A-Za-z][A-Za-z0-9._-]{0,63}$/;

/**
 * A controlled outcome code. Lowercase snake_case only, so free text, source
 * code, paths and multi-line payloads can never satisfy it.
 */
const CODE_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;

/** A controlled result token, same grammar as an outcome code. */
const OUTCOME_PATTERN = CODE_PATTERN;

/**
 * The correlation-ID grammar. Identical to the inbound `X-Request-Id` rule in
 * x-request-id.ts, so a value that was accepted from a client and a value that
 * was generated locally are indistinguishable downstream and equally safe.
 */
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._~-]{1,128}$/;

/** Longest request path retained in a log line. */
const MAX_PATH_LENGTH = 256;

/** Longest correlation ID retained in a log line. */
const MAX_REQUEST_ID_LENGTH = 128;

// C0 and C1 control characters, minus nothing: TAB (U+0009) and DEL (U+007F)
// are stripped too, because none of them carry meaning in a log line and all of
// them can disrupt terminal rendering or line-based log parsing.
//
// This is a code-point range comparison rather than a character class on
// purpose. The equivalent /[\u0000-\u001F\u007F-\u009F]/g trips no-control-regex,
// and suppressing that rule would silence a genuine control-character bug in
// any future edit to the same line. Comparing the boundary values explicitly
// keeps the lint rule active everywhere else in the file.
const C0_LAST = 0x1f;
const C1_FIRST = 0x7f;
const C1_LAST = 0x9f;

function isControlChar(codePoint: number): boolean {
  return codePoint <= C0_LAST || (codePoint >= C1_FIRST && codePoint <= C1_LAST);
}

/**
 * Removes control characters and truncates.
 *
 * Applied before every format check as defence in depth. The format patterns
 * already reject CR/LF, so this is a second, independent barrier rather than the
 * primary defence.
 */
function stripControlChars(value: string, maxLength: number): string {
  const cleaned = Array.from(value)
    .filter((char) => !isControlChar(char.codePointAt(0) ?? 0))
    .join('');

  return cleaned.length > maxLength ? cleaned.slice(0, maxLength) : cleaned;
}

/**
 * Reduces any URL-ish value to a bare path with credentials and query removed.
 *
 * `http://user:secret@host:8000/api/v1/x?token=abc` becomes `/api/v1/x`. The
 * credentials and the query string are discarded entirely rather than masked,
 * so neither can reach the sink at all.
 */
function toSafePath(value: string): string {
  let candidate = stripControlChars(value, MAX_PATH_LENGTH * 2);

  if (candidate.includes('://')) {
    try {
      const url = new URL(candidate);
      // username/password are intentionally not carried over, and the search and
      // hash components are dropped because tokens are commonly passed there.
      candidate = url.pathname;
    } catch {
      return '';
    }
  } else {
    // Strip any query or fragment that arrived without a scheme.
    const cut = candidate.search(/[?#]/);
    if (cut !== -1) candidate = candidate.slice(0, cut);
  }

  return stripControlChars(candidate, MAX_PATH_LENGTH);
}

// ---------------------------------------------------------------------------
// Sanitizer
// ---------------------------------------------------------------------------

/**
 * Sanitizes an untrusted field set down to the allowlisted, format-checked set.
 *
 * Only keys present in ALLOWED_LOG_FIELDS are ever read from `fields`, so an
 * unknown key cannot pass through even if it holds harmless-looking data. The
 * returned object is always freshly allocated; the input is never mutated.
 */
export function redactLogFields(fields: UntrustedLogFields): StructuredLogFields {
  const safe: StructuredLogFields = {};
  if (fields === null || typeof fields !== 'object') return safe;

  for (const key of ALLOWED_LOG_FIELDS) {
    const value = fields[key];
    if (value === undefined || value === null) continue;

    switch (key) {
      case 'operation': {
        if (typeof value !== 'string') break;
        const cleaned = stripControlChars(value, 64);
        if (OPERATION_PATTERN.test(cleaned)) safe.operation = cleaned;
        break;
      }

      case 'path': {
        if (typeof value !== 'string') break;
        const cleaned = toSafePath(value);
        if (cleaned.length > 0 && cleaned.startsWith('/')) safe.path = cleaned;
        break;
      }

      case 'status': {
        if (typeof value !== 'number') break;
        if (Number.isInteger(value) && value >= 100 && value <= 599) {
          safe.status = value;
        }
        break;
      }

      case 'durationMs': {
        if (typeof value !== 'number') break;
        if (Number.isFinite(value) && value >= 0) safe.durationMs = value;
        break;
      }

      case 'code': {
        if (typeof value !== 'string') break;
        const cleaned = stripControlChars(value, 64);
        if (CODE_PATTERN.test(cleaned)) safe.code = cleaned;
        break;
      }

      case 'requestId': {
        if (typeof value !== 'string') break;
        // Length is validated BEFORE any truncation. Truncating first would let
        // an oversized ID pass by shortening it to the maximum, and the ID that
        // reached the log would then differ from the one the client supplied,
        // which defeats the purpose of echoing a correlation ID. An over-long
        // value is rejected outright instead.
        if (value.length > MAX_REQUEST_ID_LENGTH) break;
        const cleaned = stripControlChars(value, MAX_REQUEST_ID_LENGTH);
        if (REQUEST_ID_PATTERN.test(cleaned)) safe.requestId = cleaned;
        break;
      }

      case 'outcome': {
        if (typeof value !== 'string') break;
        const cleaned = stripControlChars(value, 64);
        if (OUTCOME_PATTERN.test(cleaned)) safe.outcome = cleaned;
        break;
      }
    }
  }

  return safe;
}

/**
 * Renders a constant message plus sanitized fields into a single log line.
 *
 * The message is passed through unchanged by design: callers supply a constant
 * template (for example 'ai_engine_interaction'), never user data. All
 * variable content arrives via `fields` and is therefore sanitized, so this
 * function is not itself an injection vector.
 */
export function formatLogMessage(
  message: string,
  fields: StructuredLogFields,
): string {
  const keys = Object.keys(fields);
  if (keys.length === 0) return message;
  return `${message} ${JSON.stringify(fields)}`;
}
