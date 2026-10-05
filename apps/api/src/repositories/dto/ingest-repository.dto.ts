import { IsString, Matches } from 'class-validator';

/**
 * Request body for POST /repositories/ingest.
 *
 * The `repositoryPath` is an absolute path on the server's filesystem.
 * It is validated by the global ValidationPipe (whitelist + forbidNonWhitelisted)
 * before it reaches RepositoriesService, so the service receives a non-blank
 * string and can proceed directly to filesystem checks.
 *
 * MAINTENANCE: whitelist:true means every property here MUST carry a
 * class-validator decorator or @Allow(), otherwise it is silently stripped.
 */
export class IngestRepositoryDto {
  @IsString()
  @Matches(/\S/, { message: 'repositoryPath must not be blank' })
  repositoryPath!: string;
}
