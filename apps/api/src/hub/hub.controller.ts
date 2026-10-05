import { Body, Controller, Post } from '@nestjs/common';
import { HubService } from './hub.service.js';
import { AskDto, DebugDto, IndexRepositoryDto } from './dto/hub.dto.js';

@Controller('hub')
export class HubController {
  constructor(private readonly hubService: HubService) {}

  /**
   * POST /hub/repository/index
   *
   * Warm-start the AI Engine's in-memory index for the given repository.
   * Subsequent /ask and /debug calls will be faster after this call.
   */
  @Post('repository/index')
  async indexRepository(
    @Body() dto: IndexRepositoryDto,
  ): Promise<{ indexed: boolean; path: string }> {
    return this.hubService.indexRepository(dto.repositoryPath);
  }

  /**
   * POST /hub/ask
   *
   * Answer a natural-language question about the repository.
   * Returns a grounded answer with source-backed evidence.
   */
  @Post('ask')
  async ask(
    @Body() dto: AskDto,
  ) {
    const result = await this.hubService.ask(dto.question, dto.repositoryPath);
    return {
      answer: result.answer,
      evidence: result.evidence.map((e) => ({
        file: e.file,
        symbol: e.symbol,
        startLine: e.startLine,
        endLine: e.endLine,
        hasCode: e.code !== undefined && e.code.trim().length > 0,
      })),
      confidence: result.confidence,
      enrichedSummary: result.enrichedSummary ?? null,
    };
  }

  /**
   * POST /hub/debug
   *
   * Identify the root cause of an issue and suggest a fix.
   * Returns a structured debug analysis with source-backed evidence.
   */
  @Post('debug')
  async debug(
    @Body() dto: DebugDto,
  ) {
    const result = await this.hubService.debug(dto.issue, dto.repositoryPath);
    return {
      rootCause: result.rootCause,
      fix: result.fix,
      evidence: result.evidence.map((e) => ({
        file: e.file,
        symbol: e.symbol,
        startLine: e.startLine,
        endLine: e.endLine,
        hasCode: e.code !== undefined && e.code.trim().length > 0,
      })),
      confidence: result.confidence,
      enrichedSummary: result.enrichedSummary ?? null,
    };
  }
}
