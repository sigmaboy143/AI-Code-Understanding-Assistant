import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { promises as fs } from 'fs';
import * as path from 'path';
import type { IngestionResult } from './models/source-file.model.js';
import { FileScannerService } from './scanner/file-scanner.service.js';

/**
 * RepositoriesService — Phase 1: repository ingestion.
 *
 * Owns the entry point for scanning a repository from disk. Validation of the
 * path (existence, directory check, path normalisation) lives here so that
 * FileScannerService can focus purely on walking the directory tree.
 *
 * Later phases will extend this service with AST parsing and symbol extraction
 * without changing the FileScannerService contract.
 */
@Injectable()
export class RepositoriesService {
  constructor(private readonly fileScanner: FileScannerService) {}

  /**
   * Ingests a repository at the given path.
   *
   * Validates the path, resolves it to an absolute canonical form, and
   * delegates the recursive file scan to FileScannerService.
   *
   * @param repositoryPath  Absolute path to the repository root directory.
   * @returns               IngestionResult with metadata for every supported
   *                        source file found under repositoryPath.
   * @throws BadRequestException  When repositoryPath is a file, not a directory.
   * @throws NotFoundException    When repositoryPath does not exist.
   */
  async ingestRepository(repositoryPath: string): Promise<IngestionResult> {
    // Resolve to an absolute, normalized path. path.resolve handles both
    // relative and absolute inputs. The result uses the platform separator,
    // which is fine — FileScannerService normalizes to POSIX internally.
    const resolvedPath = path.resolve(repositoryPath);

    // Existence and type check.
    let stat;
    try {
      stat = await fs.stat(resolvedPath);
    } catch {
      throw new NotFoundException(
        `Repository path does not exist: ${repositoryPath}`,
      );
    }

    if (!stat.isDirectory()) {
      throw new BadRequestException(
        `Repository path is not a directory: ${repositoryPath}`,
      );
    }

    const files = await this.fileScanner.scanRepository(resolvedPath);

    return {
      repositoryRoot: resolvedPath,
      files,
      scannedAt: new Date().toISOString(),
    };
  }
}
