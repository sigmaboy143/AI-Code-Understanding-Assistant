import {
  ValidationPipe,
  type ValidationPipeOptions,
} from '@nestjs/common';

/**
 * Shared inbound-validation configuration for the whole application.
 *
 * Registered once as an APP_PIPE provider so it applies to every route without
 * any per-controller wiring. `createValidationPipe()` is the single place the
 * options below are turned into a live pipe.
 *
 * Option rationale:
 *
 * - `whitelist: true` strips any request property that carries no validation
 *   metadata. See the maintenance hazard note below.
 * - `forbidNonWhitelisted: true` turns that stripping into a 400 instead of
 *   silently dropping the field, so a client typo is reported rather than
 *   quietly ignored.
 * - `transform: true` makes NestJS run plainToInstance() so the controller
 *   receives a real DTO instance rather than a raw plain object.
 * - `enableImplicitConversion: false` keeps payloads un-coerced. Converting a
 *   value would mask malformed input (for example a numeric `code` becoming the
 *   string "42") instead of rejecting it.
 *
 * MAINTENANCE HAZARD — `whitelist: true` deletes every request property that has
 * no validation metadata. A property added to a DTO without a decorator, and
 * without `@Allow()`, is silently stripped from every request: the controller
 * receives `undefined` and no error is raised anywhere. Every property on every
 * DTO must therefore carry either a validation decorator or `@Allow()`.
 */
export const validationPipeOptions: ValidationPipeOptions = {
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
  transformOptions: {
    enableImplicitConversion: false,
  },
};

/**
 * Builds the application-wide `ValidationPipe` from `validationPipeOptions`.
 *
 * Intended for use as the `useFactory` of an `APP_PIPE` provider, which causes
 * NestJS to instantiate it once during bootstrap and apply it to every route.
 * Each call returns a fresh pipe instance.
 */
export function createValidationPipe(): ValidationPipe {
  return new ValidationPipe(validationPipeOptions);
}
