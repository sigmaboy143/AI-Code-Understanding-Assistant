import { Controller, Get, Query } from '@nestjs/common';
import { CodeSymbol } from '../analysis/models/code-symbol.model.js';
import { SymbolsService } from './symbols.service.js';

@Controller('symbols')
export class SymbolsController {
  constructor(private readonly symbolsService: SymbolsService) {}

  @Get()
  extractSymbols(
    @Query('filePath') filePath: string,
    @Query('language') language: string,
  ): Promise<CodeSymbol[]> {
    return this.symbolsService.extractSymbols(filePath, language);
  }
}
