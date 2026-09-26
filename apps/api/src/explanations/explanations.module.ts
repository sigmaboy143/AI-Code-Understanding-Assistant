import { Module } from '@nestjs/common';
import { ExplanationsController } from './explanations.controller.js';
import { ExplanationsService } from './explanations.service.js';

@Module({
  controllers: [ExplanationsController],
  providers: [ExplanationsService],
})
export class ExplanationsModule {}
