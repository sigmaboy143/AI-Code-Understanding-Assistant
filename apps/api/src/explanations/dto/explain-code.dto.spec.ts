/**
 * Proves that all six ExplainCodeDto properties survive the application-wide
 * `whitelist: true` pass, and that @Allow() added no validation constraints.
 *
 * Why this test exists: `whitelist: true` acts on any request property that has
 * no validation metadata. ExplainCodeDto deliberately carries no validation
 * rules in this phase, so without @Allow() on all six properties the pipe would
 * strip them and POST /explanations would break. @Allow() is a preservation
 * marker only, so these tests assert both halves of that contract: the
 * properties survive, AND no constraint was introduced.
 *
 * No HTTP, no Nest bootstrap, no AI Engine involvement.
 */
import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { Allow, validate, type ValidationError } from 'class-validator';
import { ExplainCodeDto } from './explain-code.dto.js';

/** Production configuration: unknown properties are rejected, not stripped. */
const REJECT_UNKNOWN = {
  whitelist: true,
  forbidNonWhitelisted: true,
} as const;

/** The stripping path: unknown properties are deleted instead of rejected. */
const STRIP_UNKNOWN = {
  whitelist: true,
  forbidNonWhitelisted: false,
} as const;

const PAYLOAD: Record<string, unknown> = {
  language: 'typescript',
  code: 'const x = 1;',
  filePath: 'src/index.ts',
  startLine: 1,
  endLine: 20,
  detailLevel: 'detailed',
};

/**
 * Control class: `alpha` is whitelisted via @Allow(), `beta` has no metadata.
 * Used to prove the stripping mechanism is genuinely active.
 */
class ControlClass {
  @Allow()
  alpha!: string;
  beta!: string;
}

describe('ExplainCodeDto whitelist preservation', () => {
  describe('forbidNonWhitelisted: true (production configuration)', () => {
    it('produces no validation errors for a fully populated payload', async () => {
      const errors: ValidationError[] = await validate(
        plainToInstance(ExplainCodeDto, PAYLOAD),
        REJECT_UNKNOWN,
      );
      expect(errors).toEqual([]);
    });

    it('rejects an unknown property', async () => {
      const errors: ValidationError[] = await validate(
        plainToInstance(ExplainCodeDto, { ...PAYLOAD, foo: 'bar' }),
        REJECT_UNKNOWN,
      );

      expect(errors).toHaveLength(1);
      expect(errors[0]).toMatchObject({ property: 'foo' });
      expect(Object.keys(errors[0]?.constraints ?? {})).toContain(
        'whitelistValidation',
      );
    });
  });

  describe('forbidNonWhitelisted: false (the stripping path)', () => {
    it('leaves all six properties present on the validated object', async () => {
      const instance = plainToInstance(ExplainCodeDto, PAYLOAD);

      const errors: ValidationError[] = await validate(instance, STRIP_UNKNOWN);

      expect(errors).toEqual([]);
      expect(instance).toHaveProperty('language');
      expect(instance).toHaveProperty('code');
      expect(instance).toHaveProperty('filePath');
      expect(instance).toHaveProperty('startLine');
      expect(instance).toHaveProperty('endLine');
      expect(instance).toHaveProperty('detailLevel');
    });

    it('leaves every value unchanged', async () => {
      const instance = plainToInstance(ExplainCodeDto, PAYLOAD);
      await validate(instance, STRIP_UNKNOWN);

      expect(instance.language).toBe(PAYLOAD['language']);
      expect(instance.code).toBe(PAYLOAD['code']);
      expect(instance.filePath).toBe(PAYLOAD['filePath']);
      expect(instance.startLine).toBe(PAYLOAD['startLine']);
      expect(instance.endLine).toBe(PAYLOAD['endLine']);
      expect(instance.detailLevel).toBe(PAYLOAD['detailLevel']);
    });
  });

  describe('no constraints were introduced', () => {
    it('accepts wrong-typed values on every property without error', async () => {
      const instance = plainToInstance(ExplainCodeDto, {
        language: 123,
        code: null,
        filePath: 456,
        startLine: 'not-a-number',
        endLine: -1,
        detailLevel: 'not-a-real-level',
      });

      const errors: ValidationError[] = await validate(instance, REJECT_UNKNOWN);

      expect(errors).toEqual([]);
    });
  });

  describe('control: the stripping mechanism is actually active', () => {
    it('deletes a property that carries no validation metadata', async () => {
      const control = plainToInstance(ControlClass, {
        alpha: 'a',
        beta: 'b',
      });

      // Pre-condition: both properties exist before validation runs.
      expect(control).toHaveProperty('alpha');
      expect(control).toHaveProperty('beta');

      const errors: ValidationError[] = await validate(control, STRIP_UNKNOWN);

      expect(errors).toEqual([]);
      // @Allow() property survived; the undecorated property was deleted.
      expect(control).toHaveProperty('alpha');
      expect(control).not.toHaveProperty('beta');
    });
  });
});
