import { Injectable } from '@nestjs/common';
import { AnalysisService } from '../analysis/analysis.service.js';
import { AnalyzeCodeDto } from '../analysis/dto/analyze-code.dto.js';
import { ExplainCodeDto } from './dto/explain-code.dto.js';
import { ExplanationResponseDto } from './dto/explanation-response.dto.js';

@Injectable()
export class ExplanationsService {
  constructor(private readonly analysisService: AnalysisService) {}

  async explain(dto: ExplainCodeDto): Promise<ExplanationResponseDto> {
    const analyzeDto: AnalyzeCodeDto = {
      language: dto.language,
      code: dto.code,
      filePath: dto.filePath,
    };

    const result = await this.analysisService.analyzeCode(analyzeDto);

    return {
      requestId: result.requestId,
      summary: result.summary ?? 'No summary available.',
      detailed: undefined,
      confidence: result.confidence,
      referencedSymbols: result.symbols,
      generatedAt: result.analysedAt,
    };
  }
}
