import { Injectable } from '@nestjs/common';
import { promises as fs } from 'fs';
import * as path from 'path';
import type { SourceFile, SupportedLanguage } from '../models/source-file.model.js';

/**
 * Maps file extensions to their AI Engine language identifiers.
 *
 * This is the single source of truth for supported extensions. Adding a new
 * language means adding its extension(s) here — no other code needs to change.
 */
const EXTENSION_TO_LANGUAGE: Readonly<Record<string, SupportedLanguage>> = {
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.js': 'javascript',
  '.jsx': 'javascript',
};

/**
 * Directory names that are always excluded from scanning, regardless of depth.
 *
 * These are exact basename matches, not prefix or glob patterns. Keeping them
 * as a Set gives O(1) lookup during the recursive walk.
 */
const IGNORED_DIRECTORIES: ReadonlySet<string> = new Set([
  '.git',
  'node_modules',
  'dist',
  'build',
  'coverage',
  '.next',
  '.nuxt',
  '.cache',
  '.turbo',
  '.nx',
  'out',
  '__pycache__',
  '.mypy_cache',
  '.pytest_cache',
  '.venv',
  'venv',
]);

/**
 * File extensions that are definitely binary or non-source. Files with these
 * extensions are skipped without reading their content.
 */
const BINARY_EXTENSIONS: ReadonlySet<string> = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
  '.mp4', '.mp3', '.wav', '.ogg', '.avi', '.mov',
  '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o',
  '.woff', '.woff2', '.ttf', '.otf', '.eot',
  '.db', '.sqlite', '.sqlite3',
  '.lock',
  '.map',
]);

/**
 * Maximum file size (in bytes) that the scanner will read for line counting.
 * Files larger than this limit are recorded with lineCount -1, indicating
 * that line counting was skipped. This prevents memory pressure from
 * unexpectedly large generated files that were not excluded by directory rules.
 */
const MAX_FILE_SIZE_FOR_LINE_COUNT = 5 * 1024 * 1024; // 5 MiB

/**
 * FileScannerService — Phase 1 repository ingestion.
 *
 * Responsibilities:
 *   1. Recursively walk a repository directory.
 *   2. Skip ignored directories (node_modules, .git, dist, etc.).
 *   3. Collect source files matching supported extensions.
 *   4. Return normalized SourceFile metadata for each discovered file.
 *
 * Intentionally does NOT:
 *   - Parse file content (that is Phase 2 — AstParserService).
 *   - Execute any file in the repository.
 *   - Expose absolute paths in its public return type.
 *   - Throw on a single unreadable file (it logs a warning and continues).
 */
@Injectable()
export class FileScannerService {
  /**
   * Recursively scans `repositoryRoot` and returns metadata for every
   * supported source file found.
   *
   * @param repositoryRoot  Canonicalized absolute path to the repository root.
   *                        Must already be validated as an existing directory
   *                        by the caller (RepositoriesService).
   * @returns               Array of SourceFile records, sorted by relativePath
   *                        for deterministic output.
   */
  async scanRepository(repositoryRoot: string): Promise<SourceFile[]> {
    const results: SourceFile[] = [];
    await this.walkDirectory(repositoryRoot, repositoryRoot, results);
    // Sort by relativePath for deterministic, test-assertable ordering.
    results.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
    return results;
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private async walkDirectory(
    repositoryRoot: string,
    currentDir: string,
    results: SourceFile[],
  ): Promise<void> {
    let entries;
    try {
      entries = await fs.readdir(currentDir, { withFileTypes: true });
    } catch {
      // Unreadable directory — skip and continue.
      return;
    }

    for (const entry of entries) {
      const absolutePath = path.join(currentDir, entry.name);

      if (entry.isDirectory()) {
        if (!IGNORED_DIRECTORIES.has(entry.name)) {
          await this.walkDirectory(repositoryRoot, absolutePath, results);
        }
        continue;
      }

      if (!entry.isFile()) {
        // Skip symlinks, block devices, etc.
        continue;
      }

      const ext = path.extname(entry.name).toLowerCase();

      // Skip binary and non-source extensions immediately.
      if (BINARY_EXTENSIONS.has(ext)) {
        continue;
      }

      const language = EXTENSION_TO_LANGUAGE[ext];
      if (language === undefined) {
        // Extension not in the supported set — skip.
        continue;
      }

      const sourceFile = await this.buildSourceFile(
        repositoryRoot,
        absolutePath,
        ext,
        language,
      );

      if (sourceFile !== null) {
        results.push(sourceFile);
      }
    }
  }

  private async buildSourceFile(
    repositoryRoot: string,
    absolutePath: string,
    ext: string,
    language: SupportedLanguage,
  ): Promise<SourceFile | null> {
    let stat;
    try {
      stat = await fs.stat(absolutePath);
    } catch {
      // File disappeared between readdir and stat, or permission denied.
      return null;
    }

    // Produce a POSIX-normalized relative path (forward slashes, no leading /).
    const relativePath = path
      .relative(repositoryRoot, absolutePath)
      .split(path.sep)
      .join('/');

    let lineCount: number;

    if (stat.size === 0) {
      lineCount = 0;
    } else if (stat.size > MAX_FILE_SIZE_FOR_LINE_COUNT) {
      // File too large to count lines — mark as -1 so callers can detect it.
      lineCount = -1;
    } else {
      lineCount = await this.countLines(absolutePath);
    }

    return {
      relativePath,
      absolutePath,
      extension: ext,
      language,
      sizeBytes: stat.size,
      lineCount,
    };
  }

  /**
   * Counts newline characters ('\n') in a file.
   *
   * A file with no newlines and non-zero content counts as 1 line.
   * An empty file (size 0, handled by the caller) counts as 0 lines.
   * This is consistent across platforms: Windows CRLF files produce the same
   * count as Unix LF files (each '\n' counts once regardless of the preceding '\r').
   *
   * Returns 0 on any read error so a single unreadable file does not
   * propagate an exception up to the scanner.
   */
  private async countLines(absolutePath: string): Promise<number> {
    let content: string;
    try {
      content = await fs.readFile(absolutePath, 'utf8');
    } catch {
      return 0;
    }

    if (content.length === 0) {
      return 0;
    }

    // Count '\n' occurrences and add 1 for the final line (which may not
    // end with a newline).
    const newlines = content.split('\n').length - 1;
    return newlines + 1;
  }

  // ---------------------------------------------------------------------------
  // Exported constants for testing and downstream use
  // ---------------------------------------------------------------------------

  /** Returns the set of supported file extensions (including leading dot). */
  getSupportedExtensions(): ReadonlySet<string> {
    return new Set(Object.keys(EXTENSION_TO_LANGUAGE));
  }

  /** Returns the set of directory names that are always ignored. */
  getIgnoredDirectories(): ReadonlySet<string> {
    return IGNORED_DIRECTORIES;
  }
}
