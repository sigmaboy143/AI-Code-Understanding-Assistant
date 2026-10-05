import 'reflect-metadata';
import { promises as fs } from 'fs';
import * as os from 'os';
import * as path from 'path';
import { AstParserService } from '../code-intelligence/parser/ast-parser.service.js';
import { ImportExtractorService } from '../code-intelligence/extractor/import-extractor.service.js';
import { SymbolExtractorService } from '../code-intelligence/extractor/symbol-extractor.service.js';
import { RelationshipExtractorService } from '../code-intelligence/extractor/relationship-extractor.service.js';
import { RelationshipsService } from './relationships.service.js';
import { RelationshipKind } from '../analysis/models/code-relationship.model.js';

let tempDir: string;
let service: RelationshipsService;

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'anas-rels-'));
  const parser = new AstParserService();
  service = new RelationshipsService(
    new RelationshipExtractorService(
      parser,
      new ImportExtractorService(parser),
      new SymbolExtractorService(parser),
    ),
  );
});

afterEach(async () => {
  await fs.rm(tempDir, { recursive: true, force: true });
});

it('resolves relationships for a file on disk', async () => {
  const file = path.join(tempDir, 'a.ts');
  await fs.writeFile(
    file,
    `import { X } from './x.js';\nexport class A extends B implements C {}\n`,
  );
  const rels = await service.resolveRelationships(file, 'typescript');
  const kinds = rels.map((r) => r.kind);
  expect(kinds).toContain(RelationshipKind.Imports);
  expect(kinds).toContain(RelationshipKind.Extends);
  expect(kinds).toContain(RelationshipKind.Implements);
});

it('returns an empty array for a missing file', async () => {
  const rels = await service.resolveRelationships(
    path.join(tempDir, 'nope.ts'),
    'typescript',
  );
  expect(rels).toEqual([]);
});
