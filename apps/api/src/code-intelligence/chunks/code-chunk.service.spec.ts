import 'reflect-metadata';
import { CodeChunkService } from './code-chunk.service.js';
import { CodeSymbol, SymbolKind } from '../../analysis/models/code-symbol.model.js';
import {
  CodeRelationship,
  RelationshipKind,
} from '../../analysis/models/code-relationship.model.js';

const SOURCE = `import { X } from './x.js';

export function greet(name: string): string {
  return 'hi ' + name;
}
`;

function symbol(): CodeSymbol {
  return {
    id: 'sym-1',
    name: 'greet',
    kind: SymbolKind.Function,
    location: {
      filePath: 'src/a.ts',
      startLine: 3,
      endLine: 5,
      startColumn: 7,
      endColumn: 1,
    },
  };
}

let service: CodeChunkService;

beforeEach(() => {
  service = new CodeChunkService();
});

it('builds a chunk with code, lines, imports and relationships', () => {
  const relationships: CodeRelationship[] = [
    {
      id: 'rel-1',
      fromSymbolId: 'sym-1',
      toSymbolId: 'sym-2',
      kind: RelationshipKind.Calls,
      filePath: 'src/a.ts',
      line: 4,
    },
  ];
  const chunks = service.buildChunks(
    'src/a.ts',
    SOURCE,
    [symbol()],
    relationships,
    ['./x.js'],
    new Set(['greet']),
  );
  expect(chunks).toHaveLength(1);
  const chunk = chunks[0];
  expect(chunk.id).toMatch(/^[0-9a-f]{16}$/);
  expect(chunk.filePath).toBe('src/a.ts');
  expect(chunk.symbolName).toBe('greet');
  expect(chunk.kind).toBe(SymbolKind.Function);
  expect(chunk.startLine).toBe(3);
  expect(chunk.endLine).toBe(5);
  expect(chunk.code).toContain('export function greet');
  expect(chunk.imports).toEqual(['./x.js']);
  expect(chunk.exported).toBe(true);
  expect(chunk.relationshipIds).toEqual(['rel-1']);
});

it('produces deterministic ids across runs', () => {
  const a = service.buildChunks('src/a.ts', SOURCE, [symbol()], [], [], new Set());
  const b = service.buildChunks('src/a.ts', SOURCE, [symbol()], [], [], new Set());
  expect(a[0].id).toBe(b[0].id);
});

it('contains no absolute Windows paths', () => {
  const chunks = service.buildChunks(
    'src/a.ts',
    SOURCE,
    [symbol()],
    [],
    [],
    new Set(),
  );
  expect(chunks[0].filePath).not.toMatch(/^[A-Za-z]:/);
  expect(chunks[0].filePath).not.toContain('\\');
});

it('does not duplicate chunks', () => {
  const dup = [symbol(), symbol()];
  const chunks = service.buildChunks('src/a.ts', SOURCE, dup, [], [], new Set());
  expect(chunks).toHaveLength(1);
});

it('skips symbols belonging to other files', () => {
  const other: CodeSymbol = {
    ...symbol(),
    id: 'sym-2',
    name: 'other',
    location: { ...symbol().location, filePath: 'src/b.ts' },
  };
  const chunks = service.buildChunks(
    'src/a.ts',
    SOURCE,
    [other],
    [],
    [],
    new Set(),
  );
  expect(chunks).toHaveLength(0);
});
