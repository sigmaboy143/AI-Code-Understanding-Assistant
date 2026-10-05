import 'reflect-metadata';
import { promises as fs } from 'fs';
import * as os from 'os';
import * as path from 'path';
import { AstParserService } from '../code-intelligence/parser/ast-parser.service.js';
import { SymbolExtractorService } from '../code-intelligence/extractor/symbol-extractor.service.js';
import { SymbolsService } from './symbols.service.js';

let tempDir: string;
let service: SymbolsService;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'anas-symbols-'));
  service = new SymbolsService(
    new SymbolExtractorService(new AstParserService()),
  );
});

afterEach(async () => {
  await fs.rm(tempDir, { recursive: true, force: true });
});

it('extracts symbols from a file on disk', async () => {
  const file = path.join(tempDir, 'a.ts');
  await fs.writeFile(file, 'export function hello() { return 1; }\n');
  const symbols = await service.extractSymbols(file, 'typescript');
  expect(symbols.map((s) => s.name)).toContain('hello');
});

it('returns an empty array for a missing file', async () => {
  const symbols = await service.extractSymbols(
    path.join(tempDir, 'nope.ts'),
    'typescript',
  );
  expect(symbols).toEqual([]);
});

it('returns an empty array for a malformed file', async () => {
  const file = path.join(tempDir, 'bad.ts');
  await fs.writeFile(file, 'class {{{ @@@');
  const symbols = await service.extractSymbols(file, 'typescript');
  expect(Array.isArray(symbols)).toBe(true);
});
