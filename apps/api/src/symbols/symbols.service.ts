import { Injectable } from '@nestjs/common';
import { CodeSymbol } from '../analysis/models/code-symbol.model.js';

@Injectable()
export class SymbolsService {
  extractSymbols(
    _filePath: string,
    _language: string,
  ): Promise<CodeSymbol[]> {
    return Promise.resolve([]);
  }
}
