import { Injectable } from '@nestjs/common';
import { createHash } from 'crypto';
import type { TSESTree } from '@typescript-eslint/typescript-estree';
import {
  CodeSymbol,
  SymbolKind,
  type SymbolLocation,
} from '../../analysis/models/code-symbol.model.js';
import { AstParserService } from '../parser/ast-parser.service.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a stable, deterministic ID from file path + symbol name + start line. */
function symbolId(filePath: string, name: string, startLine: number): string {
  return createHash('sha1')
    .update(`${filePath}|${name}|${startLine}`)
    .digest('hex')
    .slice(0, 16);
}

function toLocation(
  filePath: string,
  loc: TSESTree.SourceLocation,
): SymbolLocation {
  return {
    filePath,
    startLine: loc.start.line,
    endLine: loc.end.line,
    startColumn: loc.start.column,
    endColumn: loc.end.column,
  };
}

function identifierName(node: TSESTree.Node | null | undefined): string | null {
  if (!node) return null;
  if (node.type === 'Identifier') return (node as TSESTree.Identifier).name;
  return null;
}

// ---------------------------------------------------------------------------
// Extraction context passed through recursive calls
// ---------------------------------------------------------------------------

interface ExtractionCtx {
  filePath: string;
  symbols: CodeSymbol[];
}

// ---------------------------------------------------------------------------

/**
 * SymbolExtractorService — Phase 3 symbol extraction.
 *
 * Walks an AST produced by AstParserService and emits CodeSymbol records
 * using the existing CodeSymbol / SymbolKind / SymbolLocation models.
 *
 * Extracts:
 *   - FunctionDeclaration / FunctionExpression (named)
 *   - ArrowFunctionExpression assigned to a variable
 *   - ClassDeclaration / ClassExpression
 *   - MethodDefinition (class methods)
 *   - TSInterfaceDeclaration
 *   - TSTypeAliasDeclaration
 *   - TSEnumDeclaration
 *   - ExportDefaultDeclaration wrapping any of the above
 */
@Injectable()
export class SymbolExtractorService {
  constructor(private readonly parser: AstParserService) {}

  /**
   * Extracts symbols from source text.
   *
   * @param source    Raw source code.
   * @param filePath  Normalized relative path (used in symbol IDs and locations).
   * @param extension File extension (.ts | .tsx | .js | .jsx).
   */
  extractFromSource(
    source: string,
    filePath: string,
    extension: string,
  ): CodeSymbol[] {
    const result = this.parser.parse(source, extension);
    if (!result.ok) {
      return [];
    }
    const ctx: ExtractionCtx = { filePath, symbols: [] };
    this.visitProgram(result.ast, ctx);
    return ctx.symbols;
  }

  // ---------------------------------------------------------------------------
  // Visitor methods
  // ---------------------------------------------------------------------------

  private visitProgram(program: TSESTree.Program, ctx: ExtractionCtx): void {
    for (const stmt of program.body) {
      this.visitStatement(stmt, ctx);
    }
  }

  private visitStatement(
    node: TSESTree.ProgramStatement,
    ctx: ExtractionCtx,
  ): void {
    switch (node.type) {
      case 'FunctionDeclaration':
        this.handleFunctionDecl(node, ctx);
        break;

      case 'ClassDeclaration':
        this.handleClassDecl(node, ctx);
        break;

      case 'VariableDeclaration':
        this.handleVariableDecl(node as TSESTree.VariableDeclaration, ctx);
        break;

      case 'TSInterfaceDeclaration':
        this.handleInterfaceDecl(node as TSESTree.TSInterfaceDeclaration, ctx);
        break;

      case 'TSTypeAliasDeclaration':
        this.handleTypeAliasDecl(node as TSESTree.TSTypeAliasDeclaration, ctx);
        break;

      case 'TSEnumDeclaration':
        this.handleEnumDecl(node as TSESTree.TSEnumDeclaration, ctx);
        break;

      case 'ExportNamedDeclaration': {
        const exp = node as TSESTree.ExportNamedDeclaration;
        if (exp.declaration) {
          this.visitStatement(
            exp.declaration as unknown as TSESTree.ProgramStatement,
            ctx,
          );
        }
        break;
      }

      case 'ExportDefaultDeclaration': {
        const def = node as TSESTree.ExportDefaultDeclaration;
        if (def.declaration) {
          this.visitStatement(
            def.declaration as unknown as TSESTree.ProgramStatement,
            ctx,
          );
        }
        break;
      }
    }
  }

  private handleFunctionDecl(
    node: TSESTree.FunctionDeclaration,
    ctx: ExtractionCtx,
  ): void {
    const name = identifierName(node.id) ?? '(anonymous)';
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, name, node.loc.start.line),
      name,
      kind: SymbolKind.Function,
      location: toLocation(ctx.filePath, node.loc),
    });
  }

  private handleClassDecl(
    node: TSESTree.ClassDeclaration | TSESTree.ClassExpression,
    ctx: ExtractionCtx,
  ): void {
    const name = identifierName(node.id) ?? '(anonymous class)';
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, name, node.loc.start.line),
      name,
      kind: SymbolKind.Class,
      location: toLocation(ctx.filePath, node.loc),
    });

    // Extract class body members (methods)
    for (const member of node.body.body) {
      if (member.type === 'MethodDefinition') {
        this.handleMethodDef(member as TSESTree.MethodDefinition, ctx, name);
      } else if (member.type === 'PropertyDefinition') {
        this.handlePropertyDef(
          member as TSESTree.PropertyDefinition,
          ctx,
          name,
        );
      }
    }
  }

  private handleMethodDef(
    node: TSESTree.MethodDefinition,
    ctx: ExtractionCtx,
    className: string,
  ): void {
    const key = node.key;
    const methodName =
      key.type === 'Identifier'
        ? `${className}.${(key as TSESTree.Identifier).name}`
        : `${className}.[computed]`;
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, methodName, node.loc.start.line),
      name: methodName,
      kind: SymbolKind.Method,
      location: toLocation(ctx.filePath, node.loc),
    });
  }

  private handlePropertyDef(
    node: TSESTree.PropertyDefinition,
    ctx: ExtractionCtx,
    className: string,
  ): void {
    // Only emit arrow-function properties as symbols; skip plain data properties
    if (!node.value) return;
    if (node.value.type !== 'ArrowFunctionExpression') return;
    const key = node.key;
    const propName =
      key.type === 'Identifier'
        ? `${className}.${(key as TSESTree.Identifier).name}`
        : `${className}.[computed]`;
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, propName, node.loc.start.line),
      name: propName,
      kind: SymbolKind.Method,
      location: toLocation(ctx.filePath, node.loc),
    });
  }

  private handleVariableDecl(
    node: TSESTree.VariableDeclaration,
    ctx: ExtractionCtx,
  ): void {
    for (const declarator of node.declarations) {
      const name = identifierName(declarator.id);
      if (!name) continue;
      if (!declarator.init) continue;
      const initType = declarator.init.type;
      if (
        initType !== 'ArrowFunctionExpression' &&
        initType !== 'FunctionExpression'
      ) {
        continue;
      }
      if (!declarator.loc) continue;
      ctx.symbols.push({
        id: symbolId(ctx.filePath, name, declarator.loc.start.line),
        name,
        kind: SymbolKind.Function,
        location: toLocation(ctx.filePath, declarator.loc),
      });
    }
  }

  private handleInterfaceDecl(
    node: TSESTree.TSInterfaceDeclaration,
    ctx: ExtractionCtx,
  ): void {
    const name = node.id.name;
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, name, node.loc.start.line),
      name,
      kind: SymbolKind.Interface,
      location: toLocation(ctx.filePath, node.loc),
    });
  }

  private handleTypeAliasDecl(
    node: TSESTree.TSTypeAliasDeclaration,
    ctx: ExtractionCtx,
  ): void {
    const name = node.id.name;
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, name, node.loc.start.line),
      name,
      kind: SymbolKind.Type,
      location: toLocation(ctx.filePath, node.loc),
    });
  }

  private handleEnumDecl(
    node: TSESTree.TSEnumDeclaration,
    ctx: ExtractionCtx,
  ): void {
    const name = node.id.name;
    if (!node.loc) return;
    ctx.symbols.push({
      id: symbolId(ctx.filePath, name, node.loc.start.line),
      name,
      kind: SymbolKind.Enum,
      location: toLocation(ctx.filePath, node.loc),
    });
  }
}
