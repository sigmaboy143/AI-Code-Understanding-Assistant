import { Module } from '@nestjs/common';
import { AnalysisController } from './analysis.controller.js';
import { AnalysisService } from './analysis.service.js';
import { ANALYSIS_PROVIDER } from './interfaces/analysis-provider.interface.js';
import { NullAnalysisProvider } from './providers/null-analysis.provider.js';

@Module({
  controllers: [AnalysisController],
  providers: [
    AnalysisService,
    {
      provide: ANALYSIS_PROVIDER,
      useClass: NullAnalysisProvider,
    },
  ],
  exports: [AnalysisService],
})
export class AnalysisModule {}
