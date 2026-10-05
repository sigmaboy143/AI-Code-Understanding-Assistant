/**
 * Source-file metadata produced by the repository scanner.
 *
 * This is the internal representation used by FileScannerService and
 * RepositoriesService. It separates the machine-specific absolute path
 * (used only for I/O inside services) from the relative path (the only path
 * exposed in API responses or analysis results).
 *
 * `absolutePath` MUST NOT be serialised into a response body or stored in
 * analysis metadata visible to callers.
 */

/**
 * Language identifier strings accepted by the AI Engine language field.
 * Extend this union when additional language support is added.
 */
export type SupportedLanguage = 'typescript' | 'javascript';

/**
 * Normalized metadata for a single source file discovered during repository
 * ingestion.
 *
 * - `relativePath`  POSIX-normalized path from the repository root.
 *                   Safe to expose in API responses and analysis metadata.
 * - `absolutePath`  Full OS path. Used only for I/O. MUST NOT appear in
 *                   any public response or analysis evidence field.
 * - `extension`     File extension including the leading dot (e.g. '.ts').
 * - `language`      Language token derived from the extension.
 * - `sizeBytes`     File size in bytes as returned by the OS stat call.
 * - `lineCount`     Number of newline-delimited lines. Empty files produce 0.
 *                   Only LF ('\n') is counted for cross-platform consistency.
 */
export interface SourceFile {
  relativePath: string;
  absolutePath: string;
  extension: string;
  language: SupportedLanguage;
  sizeBytes: number;
  lineCount: number;
}

/**
 * The complete result returned by a single repository ingestion.
 *
 * `repositoryRoot` is the canonicalized absolute path of the scanned root.
 * Kept for internal use; callers supplied the path themselves.
 */
export interface IngestionResult {
  repositoryRoot: string;
  files: SourceFile[];
  scannedAt: string;
}
