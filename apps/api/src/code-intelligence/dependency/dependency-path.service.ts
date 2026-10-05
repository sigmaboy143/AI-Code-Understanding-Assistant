import { Injectable } from '@nestjs/common';
import { CodeRelationship } from '../../analysis/models/code-relationship.model.js';
import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';

/** A single hop on a dependency path. */
export interface DependencyNode {
  symbolId: string;
  symbolName: string;
  filePath: string;
  line: number;
}

/** One edge on the path. */
export interface DependencyEdge {
  from: string;
  to: string;
  kind: string;
  line: number;
}

/** The result of a dependency path traversal. */
export interface DependencyPath {
  /** Ordered list of nodes from start to end. */
  nodes: DependencyNode[];
  /** Ordered edges connecting consecutive nodes. */
  edges: DependencyEdge[];
  /** True when traversal was stopped due to cycle detection or depth limit. */
  truncated: boolean;
}

/**
 * DependencyPathService — Phase 6 lightweight dependency traversal.
 *
 * Traces a path from a start symbol through CALLS and IMPORTS relationships
 * to produce an ordered chain useful for architecture and debugging views.
 *
 * This is intentionally NOT a full graph algorithm — it is a single-path
 * DFS with cycle prevention, suitable for the demo use case of showing
 * Controller → Service → Repository → JWT chains.
 *
 * Does NOT use a graph database. Operates directly on CodeSymbol[] and
 * CodeRelationship[] produced by the pipeline.
 */
@Injectable()
export class DependencyPathService {
  private readonly DEFAULT_MAX_DEPTH = 10;

  /**
   * Traces a dependency path starting from `startSymbolId`.
   *
   * @param startSymbolId  ID of the starting symbol.
   * @param symbols        All symbols in the repository (or relevant subset).
   * @param relationships  All relationships in the repository (or relevant subset).
   * @param maxDepth       Maximum hops before truncation (default 10).
   */
  trace(
    startSymbolId: string,
    symbols: CodeSymbol[],
    relationships: CodeRelationship[],
    maxDepth = this.DEFAULT_MAX_DEPTH,
  ): DependencyPath {
    const symbolMap = new Map<string, CodeSymbol>(
      symbols.map((s) => [s.id, s]),
    );

    // Build adjacency list: from → [relationships]
    const adjacency = new Map<string, CodeRelationship[]>();
    for (const rel of relationships) {
      const existing = adjacency.get(rel.fromSymbolId) ?? [];
      existing.push(rel);
      adjacency.set(rel.fromSymbolId, existing);
    }

    const nodes: DependencyNode[] = [];
    const edges: DependencyEdge[] = [];
    const visited = new Set<string>();
    let truncated = false;

    const startSymbol = symbolMap.get(startSymbolId);
    if (!startSymbol) {
      return { nodes: [], edges: [], truncated: false };
    }

    const dfs = (currentId: string, depth: number): void => {
      if (visited.has(currentId)) return;
      if (depth > maxDepth) {
        truncated = true;
        return;
      }

      visited.add(currentId);
      const symbol = symbolMap.get(currentId);
      if (!symbol) return;

      nodes.push({
        symbolId: symbol.id,
        symbolName: symbol.name,
        filePath: symbol.location.filePath,
        line: symbol.location.startLine,
      });

      const rels = adjacency.get(currentId) ?? [];
      for (const rel of rels) {
        const target = symbolMap.get(rel.toSymbolId);
        if (!target) continue;
        if (visited.has(rel.toSymbolId)) continue;

        edges.push({
          from: currentId,
          to: rel.toSymbolId,
          kind: rel.kind,
          line: rel.line,
        });

        dfs(rel.toSymbolId, depth + 1);
      }
    };

    dfs(startSymbolId, 0);

    return { nodes, edges, truncated };
  }
}
