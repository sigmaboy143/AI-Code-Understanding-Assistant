/**
 * Phase 4 configuration guard: pins the exact validation settings exported by
 * validation-pipe.ts and checks the factory builds a real NestJS ValidationPipe.
 *
 * Why this guard exists: these four options are the behavioural contract of the
 * application-wide pipe registered in AppModule. If one is changed or dropped —
 * say `whitelist` is turned off, or `enableImplicitConversion` is silently set
 * to true — every DTO spec and the controller integration test would still
 * describe the *intended* behaviour rather than the *actual* behaviour. A
 * drifted option could make tests pass while the running application does
 * something else. This file fails loudly instead.
 *
 * No HTTP, no module bootstrap.
 */
import { ValidationPipe } from '@nestjs/common';
import {
  createValidationPipe,
  validationPipeOptions,
} from './validation-pipe.js';

describe('validationPipeOptions', () => {
  it('enables whitelist', () => {
    expect(validationPipeOptions.whitelist).toBe(true);
  });

  it('enables forbidNonWhitelisted', () => {
    expect(validationPipeOptions.forbidNonWhitelisted).toBe(true);
  });

  it('enables transform', () => {
    expect(validationPipeOptions.transform).toBe(true);
  });

  it('disables implicit conversion', () => {
    expect(validationPipeOptions.transformOptions).toEqual({
      enableImplicitConversion: false,
    });
  });

  it('contains only the four approved settings', () => {
    // Guards against a future edit quietly adding an unapproved option, which
    // would change validation behaviour without any test noticing.
    expect(validationPipeOptions).toEqual({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
      transformOptions: {
        enableImplicitConversion: false,
      },
    });
  });
});

describe('createValidationPipe', () => {
  it('returns a NestJS ValidationPipe', () => {
    expect(createValidationPipe()).toBeInstanceOf(ValidationPipe);
  });

  it('returns a new instance on each call', () => {
    expect(createValidationPipe()).not.toBe(createValidationPipe());
  });
});
