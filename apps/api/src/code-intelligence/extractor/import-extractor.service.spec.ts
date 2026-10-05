import 'reflect-metadata';
import { AstParserService } from '../parser/ast-parser.service.js';
import { ImportExtractorService } from './import-extractor.service.js';
import { RelationshipKind } from '../../analysis/models/code-relationship.model.js';

let extractor: ImportExtractorService;

beforeEach(() => {
  extractor = new ImportExtractorService(new AstParserService());
});

function targets(source: string, ext = '.ts'): string[] {
  return extractor
    .extractFromSource(source, 'src/auth/auth.controller.ts', ext)
    .map((r) => r.toSymbolId);
}

it('extracts relative imports resolved against the importer', () => {
  const rels = extractor.extractFromSource(
    `import { AuthService } from './auth.service.js';`,
    'src/auth/auth.controller.ts',
    '.ts',
  );
  expect(rels).toHaveLength(1);
  expect(rels[0].kind).toBe(RelationshipKind.Imports);
  expect(rels[0].fromSymbolId).toBe('src/auth/auth.controller.ts');
  expect(rels[0].toSymbolId).toBe('src/auth/auth.service');
});

it('extracts parent-directory relative imports', () => {
  const rels = extractor.extractFromSource(
    `import { UserRepository } from '../users/user.repository.js';`,
    'src/auth/auth.service.ts',
    '.ts',
  );
  expect(rels[0].toSymbolId).toBe('src/users/user.repository');
});

it('extracts default imports', () => {
  expect(targets(`import React from 'react';`)).toEqual(['react']);
});

it('extracts namespace imports', () => {
  expect(targets(`import * as path from 'path';`)).toEqual(['path']);
});

it('extracts side-effect imports', () => {
  expect(targets(`import 'reflect-metadata';`)).toEqual(['reflect-metadata']);
});

it('extracts re-exports', () => {
  expect(targets(`export { AuthService } from './auth.service.js';`)).toEqual([
    'src/auth/auth.service',
  ]);
  expect(targets(`export * from './auth.service.js';`)).toEqual([
    'src/auth/auth.service',
  ]);
});

it('does not invent unresolved targets for bare specifiers', () => {
  const rels = extractor.extractFromSource(
    `import lodash from 'lodash';`,
    'src/auth/auth.controller.ts',
    '.ts',
  );
  expect(rels[0].toSymbolId).toBe('lodash');
});

it('deduplicates repeated imports of the same module', () => {
  const rels = extractor.extractFromSource(
    `import a from './x.js';\nimport b from './x.js';`,
    'src/a/main.ts',
    '.ts',
  );
  expect(rels).toHaveLength(1);
});
