/**
 * Phase 6 application logger: the only logging API application code should use.
 *
 * Two properties matter more than convenience here.
 *
 * First, every call passes through the redactor. There is no "raw" or "unsafe"
 * variant and no way to hand a LogSink to a caller, so a future contributor
 * cannot log a request body by accident: the only available method set is
 * info/warn/error, and all three sanitize. The raw sink stays private and is
 * deliberately unreachable from outside the instance.
 *
 * Second, the log level is explicit and preserved. A warn stays a warn, so
 * operator tooling can filter on severity, and so the "one AI Engine
 * interaction = one log entry" invariant can be asserted by counting entries
 * per level in a spec.
 *
 * The context tag ('AiEngineClient', and so on) is attached per instance so a
 * rendered line is attributable to its source without repeating the tag in
 * every call.
 *
 * The constructor deliberately takes the LogSink and nothing else. NestJS
 * resolves every constructor parameter it can see, so a `context: string = ...`
 * parameter would be reflected as an unresolvable String dependency and this
 * class could not be registered as a plain provider. Tags are therefore applied
 * only through withContext(), which keeps AppLogger injectable anywhere.
 */
import { Inject, Injectable } from '@nestjs/common';
import { LOG_SINK, type LogSink } from './log-sink.js';
import { redactLogFields, type LogLevel, type UntrustedLogFields } from './redact.js';

/** Default context tag when none is supplied. */
const DEFAULT_CONTEXT = 'App';

/**
 * Structured, redacting facade over the LogSink.
 *
 * Register as a provider in CommonModule and inject into any service that needs
 * to log. `withContext()` derives a differently tagged instance that shares the
 * same sink, so a component can label its own lines without a second provider.
 */
@Injectable()
export class AppLogger {
  private readonly sink: LogSink;
  private context: string;

  constructor(@Inject(LOG_SINK) sink: LogSink) {
    this.sink = sink;
    this.context = DEFAULT_CONTEXT;
  }

  /** Derives a logger carrying a different context tag over the same sink. */
  withContext(context: string): AppLogger {
    const derived = new AppLogger(this.sink);
    derived.context = context;
    return derived;
  }

  /** The context tag applied to every entry from this logger. */
  getContext(): string {
    return this.context;
  }

  info(message: string, fields?: UntrustedLogFields): void {
    this.emit('info', message, fields);
  }

  warn(message: string, fields?: UntrustedLogFields): void {
    this.emit('warn', message, fields);
  }

  error(message: string, fields?: UntrustedLogFields): void {
    this.emit('error', message, fields);
  }

  /**
   * The single emission point.
   *
   * Sanitization happens here and nowhere else, which is what guarantees the
   * invariant that no code path can bypass the allowlist. Exactly one entry is
   * written per call.
   */
  private emit(
    level: LogLevel,
    message: string,
    fields?: UntrustedLogFields,
  ): void {
    this.sink.log({
      level,
      context: this.context,
      message,
      fields: redactLogFields(fields ?? {}),
    });
  }
}
