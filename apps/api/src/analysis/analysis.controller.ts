import { Body, Controller, Post } from '@nestjs/common';
import { AnalysisService } from './analysis.service.js';
import { AnalyzeCodeDto } from './dto/analyze-code.dto.js';
import { AnalyzeFileDto } from './dto/analyze-file.dto.js';
import { AnalysisResult } from './models/analysis-result.model.js';

@Controller('analysis')
export class AnalysisController {
  constructor(private readonly analysisService: AnalysisService) {}

  @Post('code')
  analyzeCode(@Body() dto: AnalyzeCodeDto): Promise<AnalysisResult> {
    return this.analysisService.analyzeCode(dto);
  }

  @Post('file')
  analyzeFile(@Body() dto: AnalyzeFileDto): Promise<AnalysisResult> {
    return this.analysisService.analyzeFile(dto);
  }
}
