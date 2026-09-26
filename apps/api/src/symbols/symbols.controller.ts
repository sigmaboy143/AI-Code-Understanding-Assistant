import { Controller } from '@nestjs/common';
import { SymbolsService } from './symbols.service.js';

@Controller('symbols')
export class SymbolsController {
  constructor(private readonly symbolsService: SymbolsService) {}
}
