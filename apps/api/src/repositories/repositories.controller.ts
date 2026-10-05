import { Body, Controller, Post } from '@nestjs/common';
import { IngestRepositoryDto } from './dto/ingest-repository.dto.js';
import type { IngestionResult } from './models/source-file.model.js';
import { RepositoriesService } from './repositories.service.js';

/**
 * RepositoriesController — Phase 1: repository ingestion endpoint.
 *
 * POST /repositories/ingest
 *   Accepts a repositoryPath, scans the directory tree, and returns metadata
 *   for every supported source file found.
 *
 *   The global ValidationPipe (whitelist + forbidNonWhitelisted) validates
 *   IngestRepositoryDto before the handler runs, so RepositoriesService
 *   always receives a non-blank string.
 *
 *   Error responses:
 *     400  repositoryPath is blank or is not a directory.
 *     404  repositoryPath does not exist on disk.
 */
@Controller('repositories')
export class RepositoriesController {
  constructor(private readonly repositoriesService: RepositoriesService) {}

  @Post('ingest')
  ingestRepository(
    @Body() dto: IngestRepositoryDto,
  ): Promise<IngestionResult> {
    return this.repositoriesService.ingestRepository(dto.repositoryPath);
  }
}
