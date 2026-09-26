import { Module } from '@nestjs/common';
import { AnalysisController } from './analysis.controller.js';
import { AnalysisService } from './analysis.service.js';
import { AiEngineAdapterProvider } from './adapters/ai-engine.adapter.js';
import { AiEngineClient } from './adapters/ai-engine.client.js';
import {
  AI_ENGINE_CONFIG,
  createAiEngineConfig,
} from './config/ai-engine.config.js';
import { ANALYSIS_PROVIDER } from './interfaces/analysis-provider.interface.js';

@Module({
  controllers: [AnalysisController],
  providers: [
    AnalysisService,
    AiEngineClient,
    {
      provide: AI_ENGINE_CONFIG,
      useFactory: createAiEngineConfig,
    },
    {
      provide: ANALYSIS_PROVIDER,
      useClass: AiEngineAdapterProvider,
    },
  ],
  exports: [AnalysisService, AiEngineClient, AI_ENGINE_CONFIG],
})
export class AnalysisModule {}
