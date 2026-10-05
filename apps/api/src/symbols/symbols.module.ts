import { Module } from '@nestjs/common';
import { SymbolsController } from './symbols.controller.js';
import { SymbolsService } from './symbols.service.js';
import { CodeIntelligenceModule } from '../code-intelligence/code-intelligence.module.js';

@Module({
  imports: [CodeIntelligenceModule],
  controllers: [SymbolsController],
  providers: [SymbolsService],
})
export class SymbolsModule {}
