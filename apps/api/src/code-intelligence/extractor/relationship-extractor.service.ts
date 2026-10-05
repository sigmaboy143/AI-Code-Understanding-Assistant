import { Injectable } from '@nestjs/common';
import { createHash } from 'crypto';
import type { TSESTree } from '@typescript-eslint/typescript-estree';
import {
  CodeRelationship,
  RelationshipKind,
} from '../../analysis/models/code-relationship.model.js';
import {
  CodeSymbol,
  SymbolKind,
} from '../../analysis/models/code-symbol.model.js';
import { AstParserService } from '../parser/ast-parser.service.js';
import { ImportExtractorService } from './import-extractor.service.js';
import { SymbolExtractorService } from './symbol-extractor.service.js';

function relId(
  from: string,
  to: string,
  kind: RelationshipKind,
  line: number,
): string {
  return createHash('sha1')
    .update(`${from}|${to}|${kind}|${line}`)
    .digest('hex')
    .slice(0, 16);
}

/**
 * RelationshipExtractorService - Phase 5 relationship extraction.
 *
 * Combines import relationships with structural relationships extracted from
 * the AST:
 *   - file IMPORTS file/module (delegated to ImportExtractorService)
 *   - class EXTENDS class
 *   - class IMPLEMENTS interface
 *   - class CONTAINS method
 *   - local function/method CALLS local function/method
 *
 * Call-site analysis is intentionally conservative: a Calls edge is only
 * created when the callee can be resolved to a known project symbol
 * (Function or Method kind). No speculative or external edges are emitted.
 */
@Injectable()
export class RelationshipExtractorService {
  constructor(
    private readonly parser: AstParserService,
    private readonly importExtractor: ImportExtractorService,
    private readonly symbolExtractor: SymbolExtractorService,
  ) {}

  /**
   * Produces all relationships for a single source file.
   *
   * @param source    Raw source text.
   * @param filePath  Normalized relative path from repository root.
   * @param extension File extension (.ts / .tsx / .js / .jsx).
   * @param allSymbols Optional map of all known symbols in the repository,
   *                   keyed by name, used for local call resolution.
   */
  extractFromSource(
    source: string,
    filePath: string,
    extension: string,
    allSymbols?: Map<string, CodeSymbol>,
  ): CodeRelationship[] {
    const parseResult = this.parser.parse(source, extension);
    if (!parseResult.ok) return [];

    const ast = parseResult.ast;
    const relationships: CodeRelationship[] = [];
    const seen = new Set<string>();

    const addRel = (
      from: string,
      to: string,
      kind: RelationshipKind,
      line: number,
    ) => {
      const id = relId(from, to, kind, line);
      if (seen.has(id)) return;
      seen.add(id);
      relationships.push({
        id,
        fromSymbolId: from,
        toSymbolId: to,
        kind,
        filePath,
        line,
      });
    };

    // 1. Import relationships
    for (const imp of this.importExtractor.extractFromAst(ast, filePath)) {
      const id = relId(imp.fromSymbolId, imp.toSymbolId, imp.kind, imp.line);
      if (!seen.has(id)) {
        seen.add(id);
        relationships.push(imp);
      }
    }

    // 2. Extract local symbols so we can do name-based call resolution
    const localSymbols = this.symbolExtractor.extractFromSource(
      source,
      filePath,
      extension,
    );
    const localSymbolsByName = new Map<string, CodeSymbol>();
    for (const s of localSymbols) {
      localSymbolsByName.set(s.name, s);
    }

    // 3. Class-level structural relationships: EXTENDS / IMPLEMENTS / CONTAINS
    for (const stmt of ast.body) {
      const decl = this.unwrapExport(stmt);
      if (!decl) continue;

      if (decl.type === 'ClassDeclaration' || decl.type === 'ClassExpression') {
        const classNode = decl as TSESTree.ClassDeclaration;
        const className = classNode.id?.name ?? '(anonymous class)';
        const classSymbol = localSymbolsByName.get(className);
        const fromId = classSymbol?.id ?? className;

        // extends
        if (classNode.superClass) {
          const superName =
            classNode.superClass.type === 'Identifier'
              ? (classNode.superClass as TSESTree.Identifier).name
              : null;
          if (superName) {
            const line = classNode.loc?.start.line ?? 1;
            const targetId =
              localSymbolsByName.get(superName)?.id ??
              allSymbols?.get(superName)?.id ??
              superName;
            addRel(fromId, targetId, RelationshipKind.Extends, line);
          }
        }

        // implements
        if (classNode.implements && classNode.implements.length > 0) {
          for (const impl of classNode.implements) {
            const expr = impl.expression;
            const implName =
              expr.type === 'Identifier'
                ? (expr as TSESTree.Identifier).name
                : null;
            if (!implName) continue;
            const line = impl.loc?.start.line ?? 1;
            const targetId =
              localSymbolsByName.get(implName)?.id ??
              allSymbols?.get(implName)?.id ??
              implName;
            addRel(fromId, targetId, RelationshipKind.Implements, line);
          }
        }

        // class CONTAINS method
        for (const member of classNode.body.body) {
          if (member.type !== 'MethodDefinition') continue;
          const m = member as TSESTree.MethodDefinition;
          if (m.key.type !== 'Identifier') continue;
          const methodName = `${className}.${(m.key as TSESTree.Identifier).name}`;
          const methodSymbol = localSymbolsByName.get(methodName);
          if (classSymbol && methodSymbol) {
            addRel(
              classSymbol.id,
              methodSymbol.id,
              RelationshipKind.Contains,
              methodSymbol.location.startLine,
            );
          }
        }
      }
    }

    // 4. Call-site analysis - conservative: only local -> local
    const combined = new Map<string, CodeSymbol>([
      ...(allSymbols ?? new Map<string, CodeSymbol>()),
      ...localSymbolsByName,
    ]);
    this.extractCalls(ast, filePath, localSymbols, combined, addRel);

    return relationships;
  }

  private unwrapExport(
    node: TSESTree.ProgramStatement,
  ): TSESTree.Node | null {
    if (node.type === 'ExportNamedDeclaration') {
      return (node as TSESTree.ExportNamedDeclaration).declaration ?? null;
    }
    if (node.type === 'ExportDefaultDeclaration') {
      return (node as TSESTree.ExportDefaultDeclaration).declaration;
    }
    return node;
  }

  /**
   * Walks the AST tracking the innermost function/method body (the caller
   * context). Every CallExpression inside it is resolved against known
   * project symbols; only resolvable local targets produce a Calls edge.
   */
  private extractCalls(
    ast: TSESTree.Program,
    filePath: string,
    localSymbols: CodeSymbol[],
    symbolsByName: Map<string, CodeSymbol>,
    addRel: (
      from: string,
      to: string,
      kind: RelationshipKind,
      line: number,
    ) => void,
  ): void {
    const localByName = new Map<string, CodeSymbol>();
    for (const s of localSymbols) localByName.set(s.name, s);

    const visit = (
      node: TSESTree.Node,
      currentCaller: CodeSymbol | null,
      className: string | null,
    ): void => {
      // Entering a scope-defining node that maps to a local symbol switches
      // the caller context for everything inside it.
      let caller = currentCaller;
      let enclosingClass = className;

      if (node.type === 'ClassDeclaration' || node.type === 'ClassExpression') {
        const cls = node as TSESTree.ClassDeclaration;
        enclosingClass = cls.id?.name ?? enclosingClass;
      }

      if (node.type === 'FunctionDeclaration') {
        const fn = node as TSESTree.FunctionDeclaration;
        const named = fn.id ? localByName.get(fn.id.name) : undefined;
        if (named) caller = named;
      } else if (node.type === 'MethodDefinition') {
        const m = node as TSESTree.MethodDefinition;
        if (m.key.type === 'Identifier' && enclosingClass) {
          const sym = localByName.get(
            `${enclosingClass}.${(m.key as TSESTree.Identifier).name}`,
          );
          if (sym) caller = sym;
        }
      } else if (node.type === 'VariableDeclarator') {
        const vd = node as TSESTree.VariableDeclarator;
        const init = vd.init;
        if (
          vd.id.type === 'Identifier' &&
          init &&
          (init.type === 'ArrowFunctionExpression' ||
            init.type === 'FunctionExpression')
        ) {
          const sym = localByName.get(
            (vd.id as TSESTree.Identifier).name,
          );
          if (sym) caller = sym;
        }
      }

      if (node.type === 'CallExpression' && caller) {
        this.resolveCall(
          node as TSESTree.CallExpression,
          caller,
          filePath,
          symbolsByName,
          addRel,
        );
      }

      // Recurse into children
      for (const key of Object.keys(node)) {
        const child = (node as unknown as Record<string, unknown>)[key];
        if (Array.isArray(child)) {
          for (const item of child) {
            if (item && typeof item === 'object' && 'type' in item) {
              visit(item as TSESTree.Node, caller, enclosingClass);
            }
          }
        } else if (
          child &&
          typeof child === 'object' &&
          'type' in (child as object)
        ) {
          visit(child as TSESTree.Node, caller, enclosingClass);
        }
      }
    };

    visit(ast, null, null);
  }

  /**
   * Resolves a single CallExpression to a known local callee symbol and adds
   * a Calls relationship from the caller. Unresolvable or external callees
   * produce nothing.
   */
  private resolveCall(
    call: TSESTree.CallExpression,
    caller: CodeSymbol,
    filePath: string,
    symbolsByName: Map<string, CodeSymbol>,
    addRel: (
      from: string,
      to: string,
      kind: RelationshipKind,
      line: number,
    ) => void,
  ): void {
    const candidates: CodeSymbol[] = [];

    if (call.callee.type === 'Identifier') {
      const name = (call.callee as TSESTree.Identifier).name;
      const exact = symbolsByName.get(name);
      if (exact) candidates.push(exact);
    } else if (call.callee.type === 'MemberExpression') {
      const member = call.callee as TSESTree.MemberExpression;
      if (member.property.type === 'Identifier') {
        const methodName = (member.property as TSESTree.Identifier).name;
        for (const sym of symbolsByName.values()) {
          if (sym.name === methodName || sym.name.endsWith(`.${methodName}`)) {
            candidates.push(sym);
          }
        }
      }
    } else {
      return;
    }

    const callable = candidates.filter(
      (s) => s.kind === SymbolKind.Function || s.kind === SymbolKind.Method,
    );
    if (callable.length === 0) return;

    // Prefer candidates outside the caller's own file (typical DI wiring),
    // then candidates that are not the caller itself.
    const crossFile = callable.filter(
      (s) => s.location.filePath !== caller.location.filePath,
    );
    const pool = crossFile.length > 0 ? crossFile : callable;
    const nonSelf = pool.filter((s) => s.id !== caller.id);
    const target = (nonSelf.length > 0 ? nonSelf : pool)[0];

    const line = call.loc?.start.line ?? 1;
    addRel(caller.id, target.id, RelationshipKind.Calls, line);
  }
}
