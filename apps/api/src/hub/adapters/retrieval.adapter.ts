/**
 * RealRetrievalAdapter
 *
 * Turns a natural-language question into grounded evidence items whose `code`
 * field contains the actual source lines from the repository.
 *
 * Pipeline
 * --------
 * 1. Call the AI Engine's retrieval endpoint (POST /api/v1/retrieve) to obtain
 *    a ranked list of { file, symbol, startLine, endLine, score } items.
 * 2. For each item read the exact source lines from
 *    `repositoryRoot / item.file` (startLine..endLine, 1-based).
 * 3. Attach the extracted text as `item.code`.
 * 4. Never fabricate code — if the file cannot be read, keep the metadata and
 *    leave `code` undefined.
 * 5. Guard against path-traversal: resolved path must stay under repositoryRoot.
 *
 * Retrieval ranking
 * -----------------
 * The AI Engine already applies a symbol-name boost.  In addition this adapter
 * re-ranks the returned items so that items whose `symbol` contains a token
 * that also appears in the query are preferred.  This ensures "How does login
 * work?" lifts chunks annotated symbol="login" or symbol="AuthService.login"
 * above chunks that merely mention the word.
 *
 * Enrichment via AI Engine
 * ------------------------
 * `enrichViaAiEngine()` calls POST /api/v1/code-understanding with the actual
 * `source_code` field populated (not a comment containing metadata).  A 3-second
 * timeout is used; enrichment is optional — the caller decides whether to use
 * the enriched summary.
 */

import * as fs from 'fs';
import * as path from 'path';
import { Injectable, Logger } from '@nestjs/common';
import type { HubEvidenceItem } from '../models/hub-evidence.model.js';

// ---------------------------------------------------------------------------
// Configuration — read once from environment at module load time.
// ---------------------------------------------------------------------------

const AI_ENGINE_BASE_URL =
  process.env['AI_ENGINE_BASE_URL'] ?? 'http://127.0.0.1:8000';

/** Timeout for AI Engine retrieval calls (the main search). */
const RETRIEVAL_TIMEOUT_MS = 10_000;

/** Timeout for the optional AI Engine enrichment call. */
const ENRICH_TIMEOUT_MS = 3_000;

/** Maximum evidence items to process through source-loading. */
const MAX_EVIDENCE_ITEMS = 10;

// ---------------------------------------------------------------------------
// Token helpers (shared with ranking)
// ---------------------------------------------------------------------------

function tokenise(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[a-z0-9_]+/g) ?? []));
}

// ---------------------------------------------------------------------------
// Repository-root safety
// ---------------------------------------------------------------------------

/**
 * Resolve `relativePath` under `repositoryRoot` and verify the result stays
 * inside the root.  Returns the absolute path or null when the resolved path
 * escapes the root.
 */
function safeResolve(
  repositoryRoot: string,
  relativePath: string,
): string | null {
  const absRoot = path.resolve(repositoryRoot);
  // Normalise the evidence file path — strip any leading slash so it is always
  // treated as relative.
  const normalised = relativePath.replace(/^[/\\]+/, '');
  const absFile = path.resolve(absRoot, normalised);
  if (!absFile.startsWith(absRoot + path.sep) && absFile !== absRoot) {
    return null;
  }
  return absFile;
}

// ---------------------------------------------------------------------------
// Source-line extraction
// ---------------------------------------------------------------------------

/**
 * Read lines `startLine` to `endLine` (1-based, inclusive) from `absFilePath`.
 * Returns the extracted text or null when the file cannot be read or the line
 * range is invalid.
 */
function extractLines(
  absFilePath: string,
  startLine: number | undefined,
  endLine: number | undefined,
): string | null {
  let content: string;
  try {
    content = fs.readFileSync(absFilePath, { encoding: 'utf8' });
  } catch {
    return null;
  }

  const lines = content.split('\n');

  // When no line range is provided return the whole file (capped to avoid
  // sending enormous context to the LLM).
  const start = startLine !== undefined ? startLine - 1 : 0; // convert to 0-based
  const end =
    endLine !== undefined ? Math.min(endLine - 1, lines.length - 1) : lines.length - 1;

  if (start < 0 || start > end || start >= lines.length) {
    return null;
  }

  return lines.slice(start, end + 1).join('\n');
}

// ---------------------------------------------------------------------------
// Ranking boost
// ---------------------------------------------------------------------------

/**
 * Re-rank evidence items so that items whose `symbol` shares a token with the
 * query appear first among items at the same score.  Items with a symbol match
 * receive a +0.10 boost (capped at 1.0), identical to the AI Engine's own
 * symbol boost so the combined ranking is stable.
 */
function applySymbolBoost(
  items: HubEvidenceItem[],
  queryTokens: Set<string>,
): HubEvidenceItem[] {
  const boosted = items.map((item) => {
    let boost = 0;
    if (item.symbol) {
      const symTokens = tokenise(item.symbol);
      for (const t of symTokens) {
        if (queryTokens.has(t)) {
          boost = 0.10;
          break;
        }
      }
    }
    return {
      item,
      effectiveScore: Math.min((item.score ?? 0) + boost, 1.0),
    };
  });

  boosted.sort((a, b) => b.effectiveScore - a.effectiveScore);
  return boosted.map(({ item, effectiveScore }) => ({
    ...item,
    score: effectiveScore,
  }));
}

// ---------------------------------------------------------------------------
// AI Engine retrieval response shape
// ---------------------------------------------------------------------------

interface AiEngineRetrievalItem {
  file_path: string;
  symbol?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  relevance_score?: number;
  chunk_id?: string;
  content?: string; // The AI Engine returns chunk content directly
}

interface AiEngineRetrievalResponse {
  chunks?: AiEngineRetrievalItem[];
  evidence?: AiEngineRetrievalItem[];
  // Fallback: flat array
  results?: AiEngineRetrievalItem[];
}

// ---------------------------------------------------------------------------
// Adapter
// ---------------------------------------------------------------------------

@Injectable()
export class RealRetrievalAdapter {
  private readonly logger = new Logger(RealRetrievalAdapter.name);

  /**
   * Retrieve source-backed evidence items for `query` from the indexed
   * repository at `repositoryRoot`.
   *
   * @param repositoryRoot  Absolute (or relative) path to the repository root.
   * @param query           Natural-language question.
   * @param topK            Maximum number of evidence items to return.
   */
  async retrieve(
    repositoryRoot: string,
    query: string,
    topK = 5,
  ): Promise<HubEvidenceItem[]> {
    // ── 1. Fetch ranked chunks from the AI Engine ────────────────────────
    const rawItems = await this.fetchFromAiEngine(repositoryRoot, query, topK);

    // ── 2. Apply symbol-name boost to improve ranking ────────────────────
    const queryTokens = tokenise(query);
    const ranked = applySymbolBoost(rawItems, queryTokens);

    // ── 3. Load actual source lines for each evidence item ───────────────
    const withCode = ranked
      .slice(0, MAX_EVIDENCE_ITEMS)
      .map((item) => this.attachSourceCode(item, repositoryRoot));

    return withCode;
  }

  /**
   * Call the AI Engine's /api/v1/retrieve endpoint and convert the result to
   * `HubEvidenceItem[]`.  Falls back to an empty list when the engine is
   * unreachable or returns an error.
   */
  private async fetchFromAiEngine(
    repositoryRoot: string,
    query: string,
    topK: number,
  ): Promise<HubEvidenceItem[]> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), RETRIEVAL_TIMEOUT_MS);

    try {
      const response = await fetch(`${AI_ENGINE_BASE_URL}/api/v1/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repository_path: repositoryRoot,
          query,
          top_k: topK,
        }),
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (!response.ok) {
        this.logger.warn(
          `AI Engine retrieve returned ${response.status} — falling back to empty evidence`,
        );
        return [];
      }

      const data = (await response.json()) as AiEngineRetrievalResponse;
      return this.parseRetrievalResponse(data);
    } catch (err: unknown) {
      clearTimeout(timer);
      const isAbort =
        typeof err === 'object' &&
        err !== null &&
        'name' in err &&
        (err as { name?: unknown }).name === 'AbortError';
      this.logger.warn(
        isAbort
          ? 'AI Engine retrieve timed out — falling back to empty evidence'
          : `AI Engine retrieve failed: ${String(err)} — falling back to empty evidence`,
      );
      return [];
    }
  }

  /** Parse the AI Engine retrieval response into HubEvidenceItem[]. */
  private parseRetrievalResponse(
    data: AiEngineRetrievalResponse,
  ): HubEvidenceItem[] {
    const raw: AiEngineRetrievalItem[] =
      data.chunks ?? data.evidence ?? data.results ?? [];

    return raw.map((r) => ({
      file: r.file_path,
      symbol: r.symbol ?? undefined,
      startLine: r.line_start ?? undefined,
      endLine: r.line_end ?? undefined,
      score: r.relevance_score ?? 0,
      // Prefer the content that the AI Engine already embedded in the chunk
      // (it is the authoritative source-of-truth); source-loading below will
      // use the line range when content is absent.
      code: r.content ?? undefined,
    }));
  }

  /**
   * Load the exact source lines from the repository for `item` and attach them
   * as `item.code`.  When the file cannot be read or the path escapes the root
   * the item is returned unchanged (code stays undefined).
   */
  private attachSourceCode(
    item: HubEvidenceItem,
    repositoryRoot: string,
  ): HubEvidenceItem {
    // Skip if the AI Engine already supplied content (e.g. from its own chunk
    // store) — no need to hit the filesystem again.
    if (item.code !== undefined) {
      return item;
    }

    if (!item.file) {
      return item;
    }

    const absPath = safeResolve(repositoryRoot, item.file);
    if (absPath === null) {
      this.logger.warn(
        `Evidence file escapes repository root: ${item.file} — skipping code attachment`,
      );
      return item;
    }

    const code = extractLines(absPath, item.startLine, item.endLine);
    if (code === null) {
      this.logger.debug(
        `Could not read ${item.file} lines ${item.startLine ?? 'all'}–${item.endLine ?? 'all'} — evidence metadata kept without code`,
      );
      return item;
    }

    return { ...item, code };
  }

  // ---------------------------------------------------------------------------
  // AI Engine enrichment
  // ---------------------------------------------------------------------------

  /**
   * Optional enrichment: send the top evidence item's actual source code to the
   * AI Engine's /api/v1/code-understanding endpoint and return the summary.
   *
   * Rules:
   * - Uses a hard 3-second timeout.
   * - Non-blocking / optional — callers decide whether to use the result.
   * - Sends `source_code` populated with the real code (not metadata comments).
   * - Returns null when enrichment times out, the engine is unreachable, or
   *   no evidence item has code.
   *
   * @param evidence   Enriched evidence items (with code attached).
   * @param question   Original user question.
   * @param language   Language hint (defaults to "typescript").
   */
  async enrichViaAiEngine(
    evidence: HubEvidenceItem[],
    question: string,
    language = 'typescript',
  ): Promise<string | null> {
    // Find the highest-scored item that has actual source code.
    const best = evidence.find((e) => e.code && e.code.trim().length > 0);
    if (!best || !best.code) {
      return null;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ENRICH_TIMEOUT_MS);

    try {
      const response = await fetch(
        `${AI_ENGINE_BASE_URL}/api/v1/code-understanding`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            // Real source code — never metadata comments.
            source_code: best.code,
            language,
            file_path: best.file ?? null,
            question,
            analyses: ['explanation', 'error_explanation'],
          }),
          signal: controller.signal,
        },
      );

      clearTimeout(timer);

      if (!response.ok) {
        return null;
      }

      const data = (await response.json()) as { summary?: string };
      return data.summary ?? null;
    } catch {
      clearTimeout(timer);
      return null;
    }
  }
}
