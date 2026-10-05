import { Module } from '@nestjs/common';
import { HubController } from './hub.controller.js';
import { HubService } from './hub.service.js';
import { RealRetrievalAdapter } from './adapters/retrieval.adapter.js';
import { RealGemmaAdapter } from './adapters/gemma.adapter.js';

@Module({
  controllers: [HubController],
  providers: [HubService, RealRetrievalAdapter, RealGemmaAdapter],
  exports: [HubService],
})
export class HubModule {}
