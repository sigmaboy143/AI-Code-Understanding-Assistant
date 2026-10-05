import 'reflect-metadata';
import { AstParserService } from '../parser/ast-parser.service.js';
import { SymbolExtractorService } from './symbol-extractor.service.js';
import { SymbolKind } from '../../analysis/models/code-symbol.model.js';

let extractor: SymbolExtractorService;

beforeEach(() => {
  extractor = new SymbolExtractorService(new AstParserService());
});

it('extracts function declarations', () => {
  const symbols = extractor.extractFromSource(
    'function greet(name: string): string { return name; }',
    'src/example.ts',
    '.ts',
  );
  expect(symbols).toHaveLength(1);
  expect(symbols[0].name).toBe('greet');
  expect(symbols[0].kind).toBe(SymbolKind.Function);
  expect(symbols[0].location.startLine).toBe(1);
});

it('extracts arrow functions assigned to variables', () => {
  const symbols = extractor.extractFromSource(
    'const add = (a: number, b: number) => a + b;',
    'src/example.ts',
    '.ts',
  );
  expect(symbols).toHaveLength(1);
  expect(symbols[0].name).toBe('add');
  expect(symbols[0].kind).toBe(SymbolKind.Function);
});

it('extracts classes', () => {
  const symbols = extractor.extractFromSource(
    'class Service {}',
    'src/example.ts',
    '.ts',
  );
  expect(symbols.some((s) => s.name === 'Service' && s.kind === SymbolKind.Class)).toBe(true);
});

it('extracts class methods as ClassName.method', () => {
  const symbols = extractor.extractFromSource(
    'class AuthService {\n  login(email: string) { return email; }\n}',
    'src/example.ts',
    '.ts',
  );
  const method = symbols.find((s) => s.kind === SymbolKind.Method);
  expect(method).toBeDefined();
  expect(method!.name).toBe('AuthService.login');
  expect(method!.location.startLine).toBe(2);
});

it('extracts interfaces', () => {
  const symbols = extractor.extractFromSource(
    'interface User { id: string }',
    'src/example.ts',
    '.ts',
  );
  expect(symbols[0].kind).toBe(SymbolKind.Interface);
  expect(symbols[0].name).toBe('User');
});

it('extracts type aliases', () => {
  const symbols = extractor.extractFromSource(
    'type UserId = string;',
    'src/example.ts',
    '.ts',
  );
  expect(symbols[0].kind).toBe(SymbolKind.Type);
  expect(symbols[0].name).toBe('UserId');
});

it('extracts exported declarations', () => {
  const symbols = extractor.extractFromSource(
    'export function load() {}\nexport class Repo {}\nexport interface Cfg {}',
    'src/example.ts',
    '.ts',
  );
  const names = symbols.map((s) => s.name).sort();
  expect(names).toEqual(['Cfg', 'Repo', 'load']);
});

it('extracts TSX and JSX sources without crashing', () => {
  const tsx = extractor.extractFromSource(
    'export function Button() { return <button>x</button>; }',
    'src/Button.tsx',
    '.tsx',
  );
  expect(tsx.some((s) => s.name === 'Button')).toBe(true);

  const jsx = extractor.extractFromSource(
    'export const Button = () => <button>x</button>;',
    'src/Button.jsx',
    '.jsx',
  );
  expect(jsx.some((s) => s.name === 'Button')).toBe(true);
});

it('extracts nothing from a malformed file and does not throw', () => {
  const symbols = extractor.extractFromSource(
    'class {{{ broken @@@',
    'src/example.ts',
    '.ts',
  );
  expect(Array.isArray(symbols)).toBe(true);
});

it('produces deterministic IDs', () => {
  const src = 'function a() {}\nfunction b() {}';
  const first = extractor.extractFromSource(src, 'src/example.ts', '.ts');
  const second = extractor.extractFromSource(src, 'src/example.ts', '.ts');
  expect(first.map((s) => s.id)).toEqual(second.map((s) => s.id));
});
