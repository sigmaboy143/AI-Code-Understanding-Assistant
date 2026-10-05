import { Injectable } from '@nestjs/common';
import { parse, type TSESTree } from '@typescript-eslint/typescript-estree';

export type { TSESTree };

/**
 * Parser options shared by all file types.
 * - loc:   line/column information on every node
 * - range: byte-offset start/end on every node
 * - comment: false — we do not need comments in the AST
 * - tokens: false — we do not need the token stream
 * - errorRecovery: true — keep parsing even when there are syntax errors;
 *     returns partial AST so downstream phases still get as many symbols as
 *     possible from malformed files.
 */
const BASE_OPTIONS = {
  loc: true,
  range: false,
  tokens: false,
  comment: false,
  errorRecovery: true,
} as const;

/** Outcome of a successful parse. */
export interface ParseSuccess {
  ok: true;
  ast: TSESTree.Program;
}

/** Outcome when the parser could not produce any usable AST. */
export interface ParseFailure {
  ok: false;
  error: string;
}

export type ParseResult = ParseSuccess | ParseFailure;

/**
 * AstParserService — Phase 2 AST parsing.
 *
 * Wraps @typescript-eslint/typescript-estree with consistent options for all
 * supported file types. Returns a discriminated union (ParseResult) so callers
 * never need a try/catch — a parse error is a value, not an exception.
 *
 * Never executes repository code. Never imports from the parsed file.
 */
@Injectable()
export class AstParserService {
  /**
   * Parses source text and returns a ParseResult.
   *
   * @param source    The raw source text to parse.
   * @param extension File extension (including dot) used to choose parser options.
   *                  Use '.ts' for TypeScript, '.tsx' for TSX, '.js' for JS, '.jsx' for JSX.
   */
  parse(source: string, extension: string): ParseResult {
    const normalizedExt = extension.toLowerCase();
    const jsx = normalizedExt === '.tsx' || normalizedExt === '.jsx';

    try {
      const ast = parse(source, { ...BASE_OPTIONS, jsx });
      return { ok: true, ast };
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : String(err);
      return { ok: false, error: message };
    }
  }

  /**
   * Parses a source text that is known to be TypeScript (non-JSX).
   * Convenience wrapper used by the extractor when the extension is already
   * normalised to '.ts'.
   */
  parseTypeScript(source: string): ParseResult {
    return this.parse(source, '.ts');
  }

  /**
   * Parses a source text that is known to be TSX.
   */
  parseTsx(source: string): ParseResult {
    return this.parse(source, '.tsx');
  }

  /**
   * Parses a source text that is known to be plain JavaScript (non-JSX).
   */
  parseJavaScript(source: string): ParseResult {
    return this.parse(source, '.js');
  }

  /**
   * Parses a source text that is known to be JSX.
   */
  parseJsx(source: string): ParseResult {
    return this.parse(source, '.jsx');
  }
}
