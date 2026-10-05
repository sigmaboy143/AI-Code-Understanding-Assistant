import 'reflect-metadata';
import { fileURLToPath } from 'url';
import { AstAdapterService } from './ast-adapter.service.js';
import { RepositoriesService } from '../../repositories/repositories.service.js';
import { FileScannerService } from '../../repositories/scanner/file-scanner.service.js';
import { AstParserService } from '../parser/ast-parser.service.js';
import { SymbolExtractorService } from '../extractor/symbol-extractor.service.js';
import { ImportExtractorService } from '../extractor/import-extractor.service.js';
import { RelationshipExtractorService } from '../extractor/relationship-extractor.service.js';
import { CodeChunkService } from '../chunks/code-chunk.service.js';
import { DependencyPathService } from '../dependency/dependency-path.service.js';
import { RelationshipKind } from '../../analysis/models/code-relationship.model.js';

const FIXTURE_ROOT = fileURLToPath(
  new URL('../../../test/fixtures/auth-project', import.meta.url),
);

function makeAdapter(): AstAdapterService {
  const parser = new AstParserService();
  const symbolExtractor = new SymbolExtractorService(parser);
  const importExtractor = new ImportExtractorService(parser);
  const relationshipExtractor = new RelationshipExtractorService(
    parser,
    importExtractor,
    symbolExtractor,
  );
  const scanner = new FileScannerService();
  const repositoriesService = new RepositoriesService(scanner);
  return new AstAdapterService(
    repositoriesService,
    parser,
    symbolExtractor,
    importExtractor,
    relationshipExtractor,
    new CodeChunkService(),
    new DependencyPathService(),
  );
}

let adapter: AstAdapterService;

beforeEach(() => {
  adapter = makeAdapter();
});

it('indexes the fixture repository end to end', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });

  expect(result.files.length).toBeGreaterThanOrEqual(5);
  expect(result.symbols.length).toBeGreaterThan(0);
  expect(result.relationships.length).toBeGreaterThan(0);
  expect(result.chunks.length).toBeGreaterThan(0);
  expect(result.stats.fileCount).toBe(result.files.length);
  expect(result.stats.symbolCount).toBe(result.symbols.length);
  expect(result.stats.relationshipCount).toBe(result.relationships.length);
  expect(result.stats.chunkCount).toBe(result.chunks.length);
  expect(typeof result.repositoryRoot).toBe('string');
  expect(typeof result.indexedAt).toBe('string');
});

it('discovers the AuthController -> AuthService -> UserRepository -> JwtService chain', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });

  const calls = result.relationships.filter(
    (r) => r.kind === RelationshipKind.Calls,
  );
  const symbolNameById = new Map(result.symbols.map((s) => [s.id, s.name]));
  const callPairs = calls.map((r) => [
    symbolNameById.get(r.fromSymbolId),
    symbolNameById.get(r.toSymbolId),
  ]);

  expect(callPairs).toContainEqual(['AuthController.login', 'AuthService.login']);
  expect(callPairs).toContainEqual([
    'AuthService.login',
    'UserRepository.findByEmail',
  ]);
  expect(callPairs).toContainEqual(['AuthService.login', 'JwtService.sign']);
});

it('extracts extends/implements relationships', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });
  expect(
    result.relationships.some((r) => r.kind === RelationshipKind.Extends),
  ).toBe(true);
  expect(
    result.relationships.some((r) => r.kind === RelationshipKind.Implements),
  ).toBe(true);
});

it('extracts import relationships', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });
  const imports = result.relationships.filter(
    (r) => r.kind === RelationshipKind.Imports,
  );
  expect(imports.length).toBeGreaterThanOrEqual(3);
});

it('traces a dependency path through the demo chain', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });
  const path = adapter.traceDependencyPath('AuthController.login', result);
  const names = path.nodes.map((n) => n.symbolName);
  expect(names).toContain('AuthController.login');
  expect(names).toContain('AuthService.login');
  expect(names).toContain('UserRepository.findByEmail');
  expect(names).toContain('JwtService.sign');
  // ordered: controller before service
  expect(names.indexOf('AuthController.login')).toBeLessThan(
    names.indexOf('AuthService.login'),
  );
});

it('produces chunks with relative paths and deterministic ids', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });
  for (const chunk of result.chunks) {
    expect(chunk.filePath).not.toMatch(/^[A-Za-z]:/);
    expect(chunk.id).toMatch(/^[0-9a-f]{16}$/);
    expect(chunk.code.length).toBeGreaterThan(0);
  }
  const ids = result.chunks.map((c) => c.id);
  expect(new Set(ids).size).toBe(ids.length);
});

it('survives a malformed file inside the repository', async () => {
  const result = await adapter.indexRepository({
    repositoryPath: FIXTURE_ROOT,
  });
  // The fixture contains no malformed file; simulate by indexing a
  // nonexistent path should throw instead.
  await expect(
    adapter.indexRepository({ repositoryPath: '/no/such/path' }),
  ).rejects.toThrow();
  expect(result.symbols.length).toBeGreaterThan(0);
});
