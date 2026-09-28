/**
 * Unit tests for AnalyzeCodeDto validation rules.
 *
 * These exercise class-validator directly via plainToInstance() + validate().
 * There is no HTTP, no Nest bootstrap, and no AI Engine involvement.
 */
import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { validate, type ValidationError } from 'class-validator';
import { AnalyzeCodeDto } from './analyze-code.dto.js';

const VALID_LANGUAGE = 'typescript';
const VALID_CODE = 'const x = 1;';

/** Returns the property names that failed validation for the given payload. */
async function failingProperties(payload: unknown): Promise<string[]> {
  const errors: ValidationError[] = await validate(
    plainToInstance(AnalyzeCodeDto, payload),
  );
  return errors.map((error) => error.property);
}

const ACCEPTED: Array<[string, Record<string, unknown>]> = [
  ['minimal valid request', { language: VALID_LANGUAGE, code: VALID_CODE }],
  [
    'fully populated valid request',
    {
      language: VALID_LANGUAGE,
      code: VALID_CODE,
      filePath: 'src/index.ts',
      context: 'some context',
    },
  ],
  [
    'filePath omitted',
    { language: VALID_LANGUAGE, code: VALID_CODE, context: 'some context' },
  ],
  [
    'context omitted',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: 'src/index.ts' },
  ],
  [
    'code length exactly 100000',
    { language: VALID_LANGUAGE, code: 'a'.repeat(100000) },
  ],
];

const REJECTED: Array<[string, Record<string, unknown>, string]> = [
  ['missing language', { code: VALID_CODE }, 'language'],
  ['null language', { language: null, code: VALID_CODE }, 'language'],
  ['non-string language', { language: 42, code: VALID_CODE }, 'language'],
  ['empty language', { language: '', code: VALID_CODE }, 'language'],
  ['whitespace-only language', { language: '   ', code: VALID_CODE }, 'language'],
  ['missing code', { language: VALID_LANGUAGE }, 'code'],
  ['null code', { language: VALID_LANGUAGE, code: null }, 'code'],
  ['non-string code', { language: VALID_LANGUAGE, code: 42 }, 'code'],
  ['empty code', { language: VALID_LANGUAGE, code: '' }, 'code'],
  ['whitespace-only code', { language: VALID_LANGUAGE, code: '   ' }, 'code'],
  [
    'code length 100001',
    { language: VALID_LANGUAGE, code: 'a'.repeat(100001) },
    'code',
  ],
  [
    'non-string filePath',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: 42 },
    'filePath',
  ],
  [
    'non-string context',
    { language: VALID_LANGUAGE, code: VALID_CODE, context: 42 },
    'context',
  ],
];

describe('AnalyzeCodeDto', () => {
  describe('accepted payloads', () => {
    it.each(ACCEPTED)('%s', async (_label, payload) => {
      await expect(failingProperties(payload)).resolves.toEqual([]);
    });
  });

  describe('rejected payloads', () => {
    it.each(REJECTED)('%s', async (_label, payload, property) => {
      await expect(failingProperties(payload)).resolves.toContain(property);
    });
  });

  describe('rejection counts', () => {
    it('reports exactly one failing property for a single-rule violation', async () => {
      await expect(
        failingProperties({ language: '   ', code: VALID_CODE }),
      ).resolves.toEqual(['language']);
    });

    it('reports every failing property when several rules are broken', async () => {
      await expect(
        failingProperties({ language: '', code: '' }),
      ).resolves.toEqual(expect.arrayContaining(['language', 'code']));
    });
  });
});
