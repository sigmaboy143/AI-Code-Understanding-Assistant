import { Injectable } from '@nestjs/common';
import { createHash } from 'crypto';
import * as path from 'path';
import type { TSESTree } from '@typescript-eslint/typescript-estree';
import {
  CodeRelationship,
  RelationshipKind,
} from '../../analysis/models/code-relationship.model.js';
import { AstParserService } from '../parser/ast-parser.service.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relId(
  fromSymbolId: string,
  toSymbolId: string,
  kind: RelationshipKind,
  line: number,
): string {
  return createHash('sha1')
    .update(`${fromSymbolId}|${toSymbolId}|${kind}|${line}`)
    .digest('hex')
    .slice(0, 16);
}

/**
 * Resolves a relative import path against the importer file path.
 * Returns a normalized relative path from the repository root, or the
 * specifier unchanged when it is not a relative import (e.g. 'lodash').
 *
 * Strips common Node/TS suffixes (.js extension from ESM imports that point at
 * .ts sources, index suffixes) so the resolved path is consistent with
 * FileScannerService's relativePath values.
 */
function resolveImportPath(
  importerRelativePath: string,
  specifier: string,
): string {
  if (!specifier.startsWith('.')) {
    // External / node_modules specifier — return as-is
    return specifier;
  }

  const importerDir = path.dirname(importerRelativePath).replace(/\\/g, '/');
  let resolved = path.posix.join(importerDir, specifier);

  // Strip .js suffix that TypeScript ESM uses to reference .ts files
  if (resolved.endsWith('.js')) {
    resolved = resolved.slice(0, -3);
  }
  // Strip /index suffix
  if (resolved.endsWith('/index')) {
    resolved = resolved.slice(0, -6);
  }

  return resolved;
}

// ---------------------------------------------------------------------------

/**
 * ImportExtractorService — Phase 4 import/export extraction.
 *
 * Produces CodeRelationship records with kind=Imports for every
 * ImportDeclaration and ExportDeclaration that references another module.
 *
 * fromSymbolId = the importer file path (treated as a module-level symbol ID)
 * toSymbolId   = the resolved import target
 */
@Injectable()
export class ImportExtractorService {
  constructor(private readonly parser: AstParserService) {}

  extractFromSource(
    source: string,
    filePath: string,
    extension: string,
  ): CodeRelationship[] {
    const result = this.parser.parse(source, extension);
    if (!result.ok) return [];
    return this.extractFromAst(result.ast, filePath);
  }

  extractFromAst(
    ast: TSESTree.Program,
    filePath: string,
  ): CodeRelationship[] {
    const relationships: CodeRelationship[] = [];
    const seen = new Set<string>();

    for (const node of ast.body) {
      let specifier: string | null = null;
      let line = 1;

      if (node.type === 'ImportDeclaration') {
        const imp = node as TSESTree.ImportDeclaration;
        specifier = imp.source.value;
        line = imp.loc?.start.line ?? 1;
      } else if (
        node.type === 'ExportNamedDeclaration' ||
        node.type === 'ExportAllDeclaration'
      ) {
        const exp = node as
          | TSESTree.ExportNamedDeclaration
          | TSESTree.ExportAllDeclaration;
        if (exp.source) {
          specifier = exp.source.value;
          line = exp.loc?.start.line ?? 1;
        }
      }

      if (!specifier) continue;

      const resolvedTarget = resolveImportPath(filePath, specifier);
      const key = `${filePath}|${resolvedTarget}`;
      if (seen.has(key)) continue;
      seen.add(key);

      const rel: CodeRelationship = {
        id: relId(filePath, resolvedTarget, RelationshipKind.Imports, line),
        fromSymbolId: filePath,
        toSymbolId: resolvedTarget,
        kind: RelationshipKind.Imports,
        filePath,
        line,
      };
      relationships.push(rel);
    }

    return relationships;
  }
}
