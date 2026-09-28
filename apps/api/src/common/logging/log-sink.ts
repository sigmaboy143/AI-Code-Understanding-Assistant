/**
 * Phase 6 logging sink: the seam between application code and the logger.
 *
 * Application code never touches Nest's `Logger` directly. It depends on the
 * LOG_SINK token instead, which buys two things:
 *
 * 1. Testability. A spec can swap in a recording fake and assert exactly what
 *    would have been logged, with no monkey-patching of globals and no risk of
 *    assertions passing against output the test could not actually observe.
 * 2. Replaceability. The concrete sink is an implementation detail. Moving to a
 *    structured backend later is a CommonModule change, not a change to every
 *    call site.
 *
 * The default implementation delegates to NestJS's built-in Logger. No external
 * logging package is introduced: pino, winston and nestjs-pino are all
 * deliberately out of scope, because choosing a log shipping/formatting backend
 * is an operations decision rather than a Phase 6 decision.
 */
import { Injectable, Logger } from '@nestjs/common';
import {
  formatLogMessage,
  type LogLevel,
  type StructuredLogFields,
} from './redact.js';

/**
 * Injection token for the logging sink.
 *
 * A bare string, matching the convention already used by AI_ENGINE_CONFIG and
 * ANALYSIS_PROVIDER in this codebase. Registering a fake in a spec is therefore
 * `{ provide: LOG_SINK, useValue: fakeSink }`.
 */
export const LOG_SINK = 'LOG_SINK';

/**
 * One structured log entry, already sanitized by the time it arrives here.
 *
 * The sink is downstream of the redactor and must not be treated as a place
 * where raw data is still acceptable: the interface receives a
 * StructuredLogFields, which has no member capable of holding a request or
 * response body.
 */
export interface LogEntry {
  level: LogLevel;
  context: string;
  message: string;
  fields: StructuredLogFields;
}

/** The logging contract application code depends on. */
export interface LogSink {
  log(entry: LogEntry): void;
}

/**
 * Default sink, delegating to NestJS's built-in Logger.
 *
 * Level is preserved end to end: info maps to Logger.log, warn to Logger.warn
 * and error to Logger.error, so log-level based filtering keeps working.
 * Context is forwarded as Nest's context argument, which is what makes a line
 * attributable to 'AiEngineClient' in the rendered output.
 */
@Injectable()
export class NestLoggerSink implements LogSink {
  private readonly logger = new Logger(NestLoggerSink.name);

  log(entry: LogEntry): void {
    const line = formatLogMessage(entry.message, entry.fields);

    switch (entry.level) {
      case 'warn':
        this.logger.warn(line, entry.context);
        break;
      case 'error':
        this.logger.error(line, entry.context);
        break;
      case 'info':
      default:
        this.logger.log(line, entry.context);
        break;
    }
  }
}
