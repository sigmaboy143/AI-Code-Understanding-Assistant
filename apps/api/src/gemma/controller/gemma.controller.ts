import { Controller, Post, Body, HttpCode, HttpStatus } from '@nestjs/common';
import { GemmaRequestDto } from '../dto/gemma-request.dto';
import { GemmaService } from '../service/gemma.service';
import { AnalyzeRequestDto, EvidenceItem } from '../dto/evidence-item.dto';

@Controller()
export class GemmaController {
  constructor(private readonly gemmaService: GemmaService) {}

  /**
   * POST /ai/test
   * Tests the Gemma 4 model with a simple prompt.
   */
  @Post('ai/test')
  @HttpCode(HttpStatus.OK)
  async test(@Body() dto: GemmaRequestDto): Promise<{
    success: boolean;
    model: string;
    response: string;
  }> {
    const response = await this.gemmaService.generateResponse(dto.prompt);

    return {
      success: true,
      model: 'gemma-4-26b-a4b-it',
      response,
    };
  }

  /**
   * POST /ai/analyze
   * Analyzes a developer question using a retrieved evidence pack.
   * The Gemma model answers ONLY from the supplied evidence.
   */
  @Post('ai/analyze')
  @HttpCode(HttpStatus.OK)
  async analyze(
    @Body() dto: AnalyzeRequestDto,
  ): Promise<{
    success: boolean;
    answer: string;
    evidence: EvidenceItem[];
    dependencyPath: string[];
    confidence: 'high' | 'medium' | 'low';
    insufficientEvidence: boolean;
  }> {
    const { question, evidence, dependencyPath } = dto;

    const result = await this.gemmaService.analyzeWithEvidence(
      question,
      evidence,
      dependencyPath,
    );

    return {
      success: true,
      answer: result.answer,
      evidence,
      dependencyPath: dependencyPath || [],
      confidence: result.confidence,
      insufficientEvidence: result.insufficientEvidence,
    };
  }
}