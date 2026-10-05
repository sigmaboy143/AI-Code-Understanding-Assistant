import { Module } from '@nestjs/common';
import { RepositoriesModule } from '../repositories/repositories.module.js';
import { AstParserService } from './parser/ast-parser.service.js';
import { SymbolExtractorService } from './extractor/symbol-extractor.service.js';
import { ImportExtractorService } from './extractor/import-extractor.service.js';
import { RelationshipExtractorService } from './extractor/relationship-extractor.service.js';
import { CodeChunkService } from './chunks/code-chunk.service.js';
import { DependencyPathService } from './dependency/dependency-path.service.js';
import { AstAdapterService } from './adapter/ast-adapter.service.js';
import { AstAdapterController } from './adapter/ast-adapter.controller.js';
import { ANAS_AST_ADAPTER } from './adapter/ast-adapter.interface.js';

@Module({
  imports: [RepositoriesModule],
  controllers: [AstAdapterController],
  providers: [
    AstParserService,
    SymbolExtractorService,
    ImportExtractorService,
    RelationshipExtractorService,
    CodeChunkService,
    DependencyPathService,
    {
      provide: ANAS_AST_ADAPTER,
      useClass: AstAdapterService,
    },
  ],
  exports: [
    AstParserService,
    SymbolExtractorService,
    ImportExtractorService,
    RelationshipExtractorService,
    CodeChunkService,
    DependencyPathService,
    ANAS_AST_ADAPTER,
  ],
})
export class CodeIntelligenceModule {}
