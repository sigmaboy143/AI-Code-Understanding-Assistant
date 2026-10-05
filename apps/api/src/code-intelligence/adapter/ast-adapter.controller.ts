import { Body, Controller, Post, Inject } from '@nestjs/common';
import { IndexRepositoryDto } from './index-repository.dto.js';
import {
  ANAS_AST_ADAPTER,
  type IAstAdapter,
  type RepositoryIndexResult,
} from './ast-adapter.interface.js';

/**
 * AstAdapterController — exposes the ANAS pipeline via HTTP.
 *
 * POST /repository/index
 *   Full repository scan + AST + symbols + relationships + chunks.
 *   Used by Prakash's integration layer and the VS Code extension.
 */
@Controller('repository')
export class AstAdapterController {
  constructor(
    @Inject(ANAS_AST_ADAPTER)
    private readonly adapter: IAstAdapter,
  ) {}

  @Post('index')
  indexRepository(
    @Body() dto: IndexRepositoryDto,
  ): Promise<RepositoryIndexResult> {
    return this.adapter.indexRepository({
      repositoryPath: dto.repositoryPath,
    });
  }
}
