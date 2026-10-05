import { Module } from '@nestjs/common';
import { GemmaService } from './service/gemma.service.js';
import { GemmaController } from './controller/gemma.controller.js';
import { GemmaRequestDto } from './dto/gemma-request.dto.js';

@Module({
  controllers: [GemmaController],
  providers: [GemmaService],
  exports: [GemmaService],
})
export class GemmaModule {}