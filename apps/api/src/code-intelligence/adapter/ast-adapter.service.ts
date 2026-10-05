import { Injectable } from '@nestjs/common';
import { promises as fs } from 'fs';
import type {
  IAstAdapter,
  RepositoryIndexRequest,
  RepositoryIndexResult,
} from './ast-adapter.interface.js';
import { RepositoriesService } from '../../repositories/repositories.service.js';
import { AstParserService } from '../parser/ast-parser.service.js';
import { SymbolExtractorService } from '../extractor/symbol-extractor.service.js';
import { ImportExtractorService } from '../extractor/import-extractor.service.js';
import { RelationshipExtractorService } from '../extractor/relationship-extractor.service.js';
import { CodeChunkService } from '../chunks/code-chunk.service.js';
import { DependencyPathService, type DependencyPath } from '../dependency/dependency-path.service.js';
import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';
import { CodeRelationship } from '../../analysis/models/code-relationship.model.js';

/**
 * AstAdapterService — the real IAstAdapter implementation.
 *
 * Orchestrates the complete ANAS pipeline for a repository:
 *   FileScannerService → AstParserService → SymbolExtractorService
 *   → ImportExtractorService → RelationshipExtractorService
 *   → CodeChunkService → RepositoryIndexResult
 *
 * This is ANAS's primary integration point. Dinesh, Yashwanth, and Prakash
 * consume its output via the /repository/index endpoint.
 */
@Injectable()
export class AstAdapterService implements IAstAdapter {
  constructor(
    private readonly repositoriesService: RepositoriesService,
    private readonly parser: AstParserService,
    private readonly symbolExtractor: SymbolExtractorService,
    private readonly importExtractor: ImportExtractorService,
    private readonly relationshipExtractor: RelationshipExtractorService,
    private readonly chunkService: CodeChunkService,
    private readonly dependencyPath: DependencyPathService,
  ) {}

  async indexRepository(
    request: RepositoryIndexRequest,
  ): Promise<RepositoryIndexResult> {
    // Phase 1: file scan + validation
    const ingestion = await this.repositoriesService.ingestRepository(
      request.repositoryPath,
    );

    const allSymbols: CodeSymbol[] = [];
    const allRelationships: CodeRelationship[] = [];

    // Phase 2+3: parse + extract symbols per file
    for (const file of ingestion.files) {
      let source: string;
      try {
        source = await fs.readFile(file.absolutePath, 'utf8');
      } catch {
        continue;
      }
      const symbols = this.symbolExtractor.extractFromSource(
        source,
        file.relativePath,
        file.extension,
      );
      allSymbols.push(...symbols);
    }

    // Build a name-indexed symbol map for cross-file call resolution
    const symbolsByName = new Map<string, CodeSymbol>(
      allSymbols.map((s) => [s.name, s]),
    );

    // Phase 4+5: import + relationship extraction per file
    for (const file of ingestion.files) {
      let source: string;
      try {
        source = await fs.readFile(file.absolutePath, 'utf8');
      } catch {
        continue;
      }
      const rels = this.relationshipExtractor.extractFromSource(
        source,
        file.relativePath,
        file.extension,
        symbolsByName,
      );
      allRelationships.push(...rels);
    }

    // Deduplicate relationships by ID
    const relMap = new Map<string, CodeRelationship>(
      allRelationships.map((r) => [r.id, r]),
    );
    const dedupedRelationships = [...relMap.values()];

    // Phase 7: build code chunks per file
    const allChunks = [];
    for (const file of ingestion.files) {
      let source: string;
      try {
        source = await fs.readFile(file.absolutePath, 'utf8');
      } catch {
        continue;
      }

      const fileSymbols = allSymbols.filter(
        (s) => s.location.filePath === file.relativePath,
      );

      // Gather import paths for this file
      const parseResult = this.parser.parse(source, file.extension);
      const importPaths: string[] = [];
      const exportedNames = new Set<string>();
      if (parseResult.ok) {
        for (const node of parseResult.ast.body) {
          if (node.type === 'ImportDeclaration') {
            importPaths.push((node as any).source.value as string);
          }
          if (
            node.type === 'ExportNamedDeclaration' ||
            node.type === 'ExportDefaultDeclaration'
          ) {
            const decl = (node as any).declaration;
            if (decl?.id?.name) exportedNames.add(decl.id.name as string);
          }
        }
      }

      const chunks = this.chunkService.buildChunks(
        file.relativePath,
        source,
        fileSymbols,
        dedupedRelationships,
        importPaths,
        exportedNames,
      );
      allChunks.push(...chunks);
    }

    return {
      repositoryRoot: ingestion.repositoryRoot,
      indexedAt: ingestion.scannedAt,
      files: ingestion.files,
      symbols: allSymbols,
      relationships: dedupedRelationships,
      chunks: allChunks,
      stats: {
        fileCount: ingestion.files.length,
        symbolCount: allSymbols.length,
        relationshipCount: dedupedRelationships.length,
        chunkCount: allChunks.length,
      },
    };
  }

  traceDependencyPath(
    symbolName: string,
    result: RepositoryIndexResult,
  ): DependencyPath {
    const symbol = result.symbols.find((s) => s.name === symbolName);
    if (!symbol) {
      return { nodes: [], edges: [], truncated: false };
    }
    return this.dependencyPath.trace(
      symbol.id,
      result.symbols,
      result.relationships,
    );
  }
}
