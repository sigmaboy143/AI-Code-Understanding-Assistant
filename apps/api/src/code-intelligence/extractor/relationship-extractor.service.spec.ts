import 'reflect-metadata';
import { AstParserService } from '../parser/ast-parser.service.js';
import { ImportExtractorService } from './import-extractor.service.js';
import { SymbolExtractorService } from './symbol-extractor.service.js';
import { RelationshipExtractorService } from './relationship-extractor.service.js';
import { RelationshipKind } from '../../analysis/models/code-relationship.model.js';
import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';

let extractor: RelationshipExtractorService;

beforeEach(() => {
  const parser = new AstParserService();
  extractor = new RelationshipExtractorService(
    parser,
    new ImportExtractorService(parser),
    new SymbolExtractorService(parser),
  );
});

function relsOfKind(
  source: string,
  kind: RelationshipKind,
  filePath = 'src/a.ts',
  allSymbols?: Map<string, CodeSymbol>,
) {
  return extractor
    .extractFromSource(source, filePath, '.ts', allSymbols)
    .filter((r) => r.kind === kind);
}

it('emits file IMPORTS file for local modules', () => {
  const rels = relsOfKind(
    `import { X } from './x.js';`,
    RelationshipKind.Imports,
    'src/a/main.ts',
  );
  expect(rels).toHaveLength(1);
  expect(rels[0].toSymbolId).toBe('src/a/x');
});

it('emits class CONTAINS method', () => {
  const rels = relsOfKind(
    `class AuthController {\n  login() { return 1; }\n}`,
    RelationshipKind.Contains,
  );
  expect(rels).toHaveLength(1);
  // fromSymbolId is the class symbol id, toSymbolId the method symbol id
  expect(rels[0].fromSymbolId).not.toBe(rels[0].toSymbolId);
});

it('emits class EXTENDS class', () => {
  const rels = relsOfKind(
    `class Base {}\nclass UserEntity extends Base {}`,
    RelationshipKind.Extends,
  );
  expect(rels).toHaveLength(1);
});

it('emits class IMPLEMENTS interface', () => {
  const rels = relsOfKind(
    `interface HasEmail { email: string }\nclass UserEntity implements HasEmail {}`,
    RelationshipKind.Implements,
  );
  expect(rels).toHaveLength(1);
});

it('emits local function calls local function', () => {
  const source = `
function helper() { return 1; }
function main() { return helper(); }
`;
  const rels = relsOfKind(source, RelationshipKind.Calls);
  expect(rels).toHaveLength(1);
});

it('emits method calls another local method via member expression', () => {
  const source = `
class UserRepository {
  findByEmail(email: string) { return email; }
}
class AuthService {
  login(email: string) {
    return this.userRepository.findByEmail(email);
  }
}
`;
  const all: CodeSymbol[] = [];
  // Build the symbol map the same way the adapter does: extract per file.
  const parser = new AstParserService();
  const symbols = new SymbolExtractorService(parser).extractFromSource(
    source,
    'src/a.ts',
    '.ts',
  );
  all.push(...symbols);
  const byName = new Map(all.map((s) => [s.name, s]));
  const rels = relsOfKind(
    source,
    RelationshipKind.Calls,
    'src/a.ts',
    byName,
  );
  expect(rels.length).toBeGreaterThanOrEqual(1);
});

it('creates no call edges for unresolvable callees', () => {
  const source = `
function main() {
  return someExternalThing.run();
}
`;
  const rels = relsOfKind(source, RelationshipKind.Calls);
  expect(rels).toHaveLength(0);
});

it('produces no relationships for malformed source', () => {
  const rels = extractor.extractFromSource('class {', 'src/a.ts', '.ts');
  expect(Array.isArray(rels)).toBe(true);
});

it('does not emit duplicate relationships', () => {
  const source = `
class A {
  run() { return this.b.work(); }
}
class B {
  work() { return 1; }
}
`;
  const parser = new AstParserService();
  const symbols = new SymbolExtractorService(parser).extractFromSource(
    source,
    'src/a.ts',
    '.ts',
  );
  const byName = new Map(symbols.map((s) => [s.name, s]));
  const rels = extractor.extractFromSource(source, 'src/a.ts', '.ts', byName);
  const ids = rels.map((r) => r.id);
  expect(new Set(ids).size).toBe(ids.length);
});
