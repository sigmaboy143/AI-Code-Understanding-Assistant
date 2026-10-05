import { Module } from '@nestjs/common';
import { GemmaService } from './service/gemma.service.js';
import { GemmaController } from './controller/gemma.controller.js';
import { GemmaAdapter } from './gemma.adapter.js';

@Module({
  controllers: [GemmaController],
  providers: [GemmaService, GemmaAdapter],
  exports: [GemmaService, GemmaAdapter],
})
export class GemmaModule {}
