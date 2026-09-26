import { Module } from '@nestjs/common';
import { SymbolsController } from './symbols.controller.js';
import { SymbolsService } from './symbols.service.js';

@Module({
  controllers: [SymbolsController],
  providers: [SymbolsService],
})
export class SymbolsModule {}
