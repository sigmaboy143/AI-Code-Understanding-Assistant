/**
 * A structured code chunk — a meaningful unit of source code (function,
 * method, class, interface, type) ready for Dinesh's retrieval pipeline.
 *
 * Design constraints:
 *   - `id` is deterministic (hash of filePath + symbolName + startLine).
 *   - `filePath` is the POSIX-normalized relative path from the repository root.
 *     NEVER an absolute path.
 *   - `code` is the actual source text of the chunk.
 *   - Relationship IDs reference CodeRelationship.id values.
 */
export interface CodeChunk {
  /** Deterministic chunk identifier. */
  id: string;
  /** Normalized relative path from repository root. */
  filePath: string;
  /** Symbol name (function name, class name, method name, etc.). */
  symbolName: string;
  /** Symbol kind matching SymbolKind values. */
  kind: string;
  /** First line of the chunk (1-based, inclusive). */
  startLine: number;
  /** Last line of the chunk (1-based, inclusive). */
  endLine: number;
  /** Actual source code of the chunk. */
  code: string;
  /** Local import specifiers relevant to this chunk. */
  imports: string[];
  /** Whether this symbol is exported. */
  exported: boolean;
  /** IDs of CodeRelationship records that involve this symbol. */
  relationshipIds: string[];
}
