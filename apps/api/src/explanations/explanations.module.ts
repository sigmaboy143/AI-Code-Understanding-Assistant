import { Module } from '@nestjs/common';
import { AnalysisModule } from '../analysis/analysis.module.js';
import { ExplanationsController } from './explanations.controller.js';
import { ExplanationsService } from './explanations.service.js';

@Module({
  imports: [AnalysisModule],
  controllers: [ExplanationsController],
  providers: [ExplanationsService],
})
export class ExplanationsModule {}
