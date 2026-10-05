import { Injectable } from '@nestjs/common';
import { promises as fs } from 'fs';
import { CodeSymbol } from '../analysis/models/code-symbol.model.js';
import { SymbolExtractorService } from '../code-intelligence/extractor/symbol-extractor.service.js';

const SUPPORTED_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);

/**
 * Maps the public `language` query value to a file extension. The extractor
 * only needs the extension to pick parser options (notably JSX mode).
 */
function extensionFor(filePath: string, language: string): string {
  const dotIdx = filePath.lastIndexOf('.');
  if (dotIdx >= 0) {
    const ext = filePath.slice(dotIdx).toLowerCase();
    if (SUPPORTED_EXTENSIONS.has(ext)) return ext;
  }
  switch (language.toLowerCase()) {
    case 'typescript':
    case 'ts':
      return '.ts';
    case 'tsx':
      return '.tsx';
    case 'javascript':
    case 'js':
      return '.js';
    case 'jsx':
      return '.jsx';
    default:
      return '.ts';
  }
}

@Injectable()
export class SymbolsService {
  constructor(private readonly symbolExtractor: SymbolExtractorService) {}

  /**
   * Reads a source file from disk and extracts its symbols. Returns an empty
   * array when the file cannot be read or its extension is unsupported, so a
   * malformed request never crashes the caller.
   */
  async extractSymbols(
    filePath: string,
    language: string,
  ): Promise<CodeSymbol[]> {
    let source: string;
    try {
      source = await fs.readFile(filePath, 'utf8');
    } catch {
      return [];
    }
    return this.symbolExtractor.extractFromSource(
      source,
      filePath,
      extensionFor(filePath, language),
    );
  }
}
