/**
 * Unit tests for AnalyzeFileDto validation rules.
 *
 * These exercise class-validator directly via plainToInstance() + validate().
 * There is no HTTP, no Nest bootstrap, and no AI Engine involvement.
 *
 * Note: a whitespace-only filePath is intentionally ACCEPTED in this phase.
 * AnalyzeFileDto.filePath is @IsString() + @IsNotEmpty() only, with no
 * @Matches(/\S/) rule. The 'whitespace-only filePath is accepted' case below
 * is a deliberate specification of that decision, not an oversight.
 */
import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { validate, type ValidationError } from 'class-validator';
import { AnalyzeFileDto } from './analyze-file.dto.js';

const VALID_LANGUAGE = 'typescript';
const VALID_CODE = 'const x = 1;';
const VALID_FILE_PATH = 'src/index.ts';

/** Returns the property names that failed validation for the given payload. */
async function failingProperties(payload: unknown): Promise<string[]> {
  const errors: ValidationError[] = await validate(
    plainToInstance(AnalyzeFileDto, payload),
  );
  return errors.map((error) => error.property);
}

const ACCEPTED: Array<[string, Record<string, unknown>]> = [
  [
    'valid request',
    {
      language: VALID_LANGUAGE,
      code: VALID_CODE,
      filePath: VALID_FILE_PATH,
      context: 'some context',
    },
  ],
  [
    'valid request with context omitted',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: VALID_FILE_PATH },
  ],
  [
    'whitespace-only filePath is accepted',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: '   ' },
  ],
  [
    'code length exactly 100000',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: 'a'.repeat(100000) },
  ],
];

const REJECTED: Array<[string, Record<string, unknown>, string]> = [
  ['missing language', { code: VALID_CODE, filePath: VALID_FILE_PATH }, 'language'],
  [
    'null language',
    { language: null, code: VALID_CODE, filePath: VALID_FILE_PATH },
    'language',
  ],
  [
    'non-string language',
    { language: 42, code: VALID_CODE, filePath: VALID_FILE_PATH },
    'language',
  ],
  [
    'empty language',
    { language: '', code: VALID_CODE, filePath: VALID_FILE_PATH },
    'language',
  ],
  [
    'whitespace-only language',
    { language: '   ', code: VALID_CODE, filePath: VALID_FILE_PATH },
    'language',
  ],
  ['missing code', { language: VALID_LANGUAGE, filePath: VALID_FILE_PATH }, 'code'],
  [
    'null code',
    { language: VALID_LANGUAGE, code: null, filePath: VALID_FILE_PATH },
    'code',
  ],
  [
    'non-string code',
    { language: VALID_LANGUAGE, code: 42, filePath: VALID_FILE_PATH },
    'code',
  ],
  [
    'empty code',
    { language: VALID_LANGUAGE, code: '', filePath: VALID_FILE_PATH },
    'code',
  ],
  [
    'whitespace-only code',
    { language: VALID_LANGUAGE, code: '   ', filePath: VALID_FILE_PATH },
    'code',
  ],
  [
    'code length 100001',
    { language: VALID_LANGUAGE, code: 'a'.repeat(100001), filePath: VALID_FILE_PATH },
    'code',
  ],
  ['missing filePath', { language: VALID_LANGUAGE, code: VALID_CODE }, 'filePath'],
  [
    'null filePath',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: null },
    'filePath',
  ],
  [
    'empty filePath',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: '' },
    'filePath',
  ],
  [
    'non-string filePath',
    { language: VALID_LANGUAGE, code: VALID_CODE, filePath: 42 },
    'filePath',
  ],
  [
    'non-string context',
    {
      language: VALID_LANGUAGE,
      code: VALID_CODE,
      filePath: VALID_FILE_PATH,
      context: 42,
    },
    'context',
  ],
];

describe('AnalyzeFileDto', () => {
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
});
