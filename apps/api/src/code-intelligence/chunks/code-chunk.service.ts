import { Injectable } from '@nestjs/common';
import { createHash } from 'crypto';
import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';
import { CodeRelationship } from '../../analysis/models/code-relationship.model.js';
import { CodeChunk } from './code-chunk.model.js';

function chunkId(filePath: string, symbolName: string, startLine: number): string {
  return createHash('sha1')
    .update(`chunk|${filePath}|${symbolName}|${startLine}`)
    .digest('hex')
    .slice(0, 16);
}

/**
 * CodeChunkService — Phase 7 structured code chunks.
 *
 * Converts CodeSymbol + source lines + CodeRelationship records into
 * CodeChunk objects ready for Dinesh's retrieval pipeline.
 *
 * One symbol → one chunk. The source lines are extracted by slicing the
 * original source text by line number.
 */
@Injectable()
export class CodeChunkService {
  /**
   * Produces CodeChunk records for a single file.
   *
   * @param filePath      Normalized relative path from repository root.
   * @param source        Raw source text of the file.
   * @param symbols       Symbols extracted from the file.
   * @param relationships All relationships for the repository (filtered internally).
   * @param importPaths   Import specifiers discovered in the file.
   * @param exportedNames Set of symbol names that are exported.
   */
  buildChunks(
    filePath: string,
    source: string,
    symbols: CodeSymbol[],
    relationships: CodeRelationship[],
    importPaths: string[],
    exportedNames: Set<string>,
  ): CodeChunk[] {
    const lines = source.split('\n');

    // Index relationships by symbol ID for fast lookup
    const relsBySymbol = new Map<string, CodeRelationship[]>();
    for (const rel of relationships) {
      for (const symbolId of [rel.fromSymbolId, rel.toSymbolId]) {
        const existing = relsBySymbol.get(symbolId) ?? [];
        existing.push(rel);
        relsBySymbol.set(symbolId, existing);
      }
    }

    const chunks: CodeChunk[] = [];
    const seen = new Set<string>();

    for (const symbol of symbols) {
      if (symbol.location.filePath !== filePath) continue;

      const id = chunkId(filePath, symbol.name, symbol.location.startLine);
      if (seen.has(id)) continue;
      seen.add(id);

      // Extract source lines (1-based → 0-based array index)
      const startIdx = symbol.location.startLine - 1;
      const endIdx = symbol.location.endLine - 1;
      const code = lines
        .slice(
          Math.max(0, startIdx),
          Math.min(lines.length, endIdx + 1),
        )
        .join('\n');

      const symRels = relsBySymbol.get(symbol.id) ?? [];
      const relIds = [...new Set(symRels.map((r) => r.id))];

      chunks.push({
        id,
        filePath,
        symbolName: symbol.name,
        kind: symbol.kind,
        startLine: symbol.location.startLine,
        endLine: symbol.location.endLine,
        code,
        imports: importPaths,
        exported: exportedNames.has(symbol.name),
        relationshipIds: relIds,
      });
    }

    return chunks;
  }
}
