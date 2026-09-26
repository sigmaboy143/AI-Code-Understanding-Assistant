import { Inject, Injectable } from '@nestjs/common';
import { randomUUID } from 'crypto';
import { AnalyzeCodeDto } from './dto/analyze-code.dto.js';
import { AnalyzeFileDto } from './dto/analyze-file.dto.js';
import type { IAnalysisProvider } from './interfaces/analysis-provider.interface.js';
import { ANALYSIS_PROVIDER } from './interfaces/analysis-provider.interface.js';
import { AnalysisResult } from './models/analysis-result.model.js';

@Injectable()
export class AnalysisService {
  constructor(
    @Inject(ANALYSIS_PROVIDER)
    private readonly analysisProvider: IAnalysisProvider,
  ) {}

  analyzeCode(dto: AnalyzeCodeDto): Promise<AnalysisResult> {
    return this.analysisProvider.analyzeCode({
      requestId: randomUUID(),
      language: dto.language,
      code: dto.code,
      filePath: dto.filePath,
      context: dto.context,
    });
  }

  analyzeFile(dto: AnalyzeFileDto): Promise<AnalysisResult> {
    return this.analysisProvider.analyzeCode({
      requestId: randomUUID(),
      language: dto.language,
      code: dto.code,
      filePath: dto.filePath,
      context: dto.context,
    });
  }
}
