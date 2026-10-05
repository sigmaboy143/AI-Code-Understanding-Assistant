import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';
import { CodeRelationship } from '../../analysis/models/code-relationship.model.js';
import { CodeChunk } from '../chunks/code-chunk.model.js';
import { SourceFile } from '../../repositories/models/source-file.model.js';
import { DependencyPath } from '../dependency/dependency-path.service.js';

/**
 * Request body for indexing a repository.
 * This is the NestJS-side contract for POST /repository/index.
 */
export interface RepositoryIndexRequest {
  /**
   * Absolute path on the server filesystem to the repository root.
   * Validated by RepositoriesService before being passed to the adapter.
   */
  repositoryPath: string;
}

/**
 * Fully-indexed repository output from IAstAdapter.
 *
 * This is the canonical shape Dinesh and Prakash consume.
 * DO NOT rename fields without coordinating with both consumers.
 */
export interface RepositoryIndexResult {
  /** Resolved absolute path of the scanned root (server-internal). */
  repositoryRoot: string;
  /** ISO timestamp of the scan. */
  indexedAt: string;
  /** All discovered source files with metadata. */
  files: SourceFile[];
  /** All extracted symbols across all files. */
  symbols: CodeSymbol[];
  /** All extracted relationships across all files. */
  relationships: CodeRelationship[];
  /** Structured code chunks ready for retrieval. */
  chunks: CodeChunk[];
  /** Summary statistics. */
  stats: {
    fileCount: number;
    symbolCount: number;
    relationshipCount: number;
    chunkCount: number;
  };
}

/**
 * IAstAdapter — the primary integration interface for the ANAS pipeline.
 *
 * Implementors take a repository path, run the full pipeline (scan → parse →
 * extract symbols → extract relationships → build chunks), and return a
 * RepositoryIndexResult.
 *
 * The injection token ANAS_AST_ADAPTER is used so the implementation can be
 * swapped without changing callers.
 */
export const ANAS_AST_ADAPTER = 'ANAS_AST_ADAPTER';

export interface IAstAdapter {
  /**
   * Indexes a repository and returns all extracted code intelligence.
   *
   * @throws NotFoundException   when repositoryPath does not exist.
   * @throws BadRequestException when repositoryPath is not a directory.
   */
  indexRepository(request: RepositoryIndexRequest): Promise<RepositoryIndexResult>;

  /**
   * Traces a dependency path starting from a named symbol.
   *
   * @param symbolName  Fully-qualified symbol name (e.g. "AuthController.login").
   * @param result      A previously-computed RepositoryIndexResult.
   */
  traceDependencyPath(
    symbolName: string,
    result: RepositoryIndexResult,
  ): DependencyPath;
}
