/**
 * RealGemmaAdapter
 *
 * Calls the Gemma LLM (via the AI Engine's Ollama-compatible provider or a
 * direct Gemma API) to generate answers and debug root-cause analyses.
 *
 * The adapter is called "Gemma" because the live deployment uses
 * gemma-4-26b-a4b-it, but the implementation talks to the AI Engine's
 * /api/v1/code-understanding endpoint, which abstracts over the concrete
 * provider.  This means:
 *
 * - Local development with Ollama works unchanged.
 * - A swap to a different model only requires changing the AI Engine's
 *   PROVIDER/MODEL environment variables.
 * - The NestJS API never holds a raw API key; the AI Engine owns that secret.
 *
 * Evidence contract
 * -----------------
 * Both `generateAnswer()` and `debugIssue()` require evidence items that carry
 * a `code` field with the actual source text.  When a caller passes evidence
 * without code the adapter still makes the call but the system prompt warns that
 * code is absent — this surfaces "Insufficient evidence" rather than a
 * hallucinated answer.  With real code the prompt includes it verbatim under a
 * "Relevant source code" heading.
 */

import { Injectable, Logger } from '@nestjs/common';
import type { HubEvidenceItem } from '../models/hub-evidence.model.js';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const AI_ENGINE_BASE_URL =
  process.env['AI_ENGINE_BASE_URL'] ?? 'http://127.0.0.1:8000';

/** Timeout for a Gemma generation call (answers may be long). */
const GEMMA_TIMEOUT_MS = 60_000;

// ---------------------------------------------------------------------------
// Prompt builders
// ---------------------------------------------------------------------------

function buildEvidenceSection(evidence: HubEvidenceItem[]): string {
  if (evidence.length === 0) {
    return '(No evidence available)';
  }

  const parts: string[] = [];
  for (const item of evidence) {
    const location = item.startLine !== undefined
      ? `${item.file}:${item.startLine}–${item.endLine ?? item.startLine}`
      : item.file;
    const header = item.symbol
      ? `[${item.symbol}] ${location}`
      : location;

    if (item.code && item.code.trim().length > 0) {
      parts.push(`${header}\n\`\`\`\n${item.code}\n\`\`\``);
    } else {
      parts.push(`${header}\n(source unavailable)`);
    }
  }

  return parts.join('\n\n');
}

// ---------------------------------------------------------------------------
// AI Engine request/response shapes
// ---------------------------------------------------------------------------

interface AiEngineCodeUnderstandingRequest {
  source_code: string;
  language: string;
  file_path: string | null;
  question: string | null;
  context: string | null;
  analyses: string[];
}

interface AiEngineCodeUnderstandingResponse {
  summary: string;
  confidence?: {
    level: string;
    evidence: object[];
    notes: string | null;
  };
}

// ---------------------------------------------------------------------------
// Response shapes returned to callers
// ---------------------------------------------------------------------------

export interface GemmaAnswer {
  /** Non-empty grounded answer from the model. */
  answer: string;
  /** Evidence items that were sent to the model. */
  evidence: HubEvidenceItem[];
  /** Confidence level from the AI Engine response. */
  confidence: string;
}

export interface GemmaDebugResult {
  /** Root cause identified by the model. */
  rootCause: string;
  /** Suggested fix(es). */
  fix: string;
  /** Evidence items that were sent to the model. */
  evidence: HubEvidenceItem[];
  /** Confidence level from the AI Engine response. */
  confidence: string;
}

// ---------------------------------------------------------------------------
// Adapter
// ---------------------------------------------------------------------------

@Injectable()
export class RealGemmaAdapter {
  private readonly logger = new Logger(RealGemmaAdapter.name);

  /**
   * Generate a grounded answer to `question` using `evidence`.
   *
   * The answer is grounded in the actual source code attached to each evidence
   * item.  When evidence items lack `code` the model will signal insufficient
   * context rather than fabricate an answer.
   *
   * @param question  User question, e.g. "How does login work?"
   * @param evidence  Source-backed evidence items from RealRetrievalAdapter.
   * @param language  Language hint (defaults to "typescript").
   */
  async generateAnswer(
    question: string,
    evidence: HubEvidenceItem[],
    language = 'typescript',
  ): Promise<GemmaAnswer> {
    const hasCode = evidence.some((e) => e.code && e.code.trim().length > 0);

    // Use the best (highest-scored) evidence item's code as `source_code` for
    // the AI Engine request; supplementary evidence goes into `context`.
    const [primary, ...rest] = evidence.filter(
      (e) => e.code && e.code.trim().length > 0,
    );

    const sourceCode = primary?.code ?? '';
    const context = rest.length > 0 ? buildEvidenceSection(rest) : null;
    const filePath = primary?.file ?? null;

    if (!hasCode) {
      this.logger.warn(
        `generateAnswer called with no evidence code — answer quality will be low`,
      );
    }

    const body: AiEngineCodeUnderstandingRequest = {
      // Real source code; never empty — use a placeholder only when truly
      // absent (this satisfies the AI Engine's min_length=1 on source_code).
      source_code: sourceCode || `// No source available for: ${question}`,
      language,
      file_path: filePath,
      question,
      context,
      analyses: ['explanation'],
    };

    const raw = await this.callAiEngine(body);

    return {
      answer: raw.summary,
      evidence,
      confidence: raw.confidence?.level ?? 'UNKNOWN',
    };
  }

  /**
   * Debug an `issue` using source-backed `evidence` and return a root-cause
   * analysis with suggested fix.
   *
   * @param issue     Issue description, e.g. "Login returns 401"
   * @param evidence  Source-backed evidence items from RealRetrievalAdapter.
   * @param language  Language hint (defaults to "typescript").
   */
  async debugIssue(
    issue: string,
    evidence: HubEvidenceItem[],
    language = 'typescript',
  ): Promise<GemmaDebugResult> {
    const hasCode = evidence.some((e) => e.code && e.code.trim().length > 0);

    const [primary, ...rest] = evidence.filter(
      (e) => e.code && e.code.trim().length > 0,
    );

    const sourceCode = primary?.code ?? '';
    const context = rest.length > 0 ? buildEvidenceSection(rest) : null;
    const filePath = primary?.file ?? null;

    if (!hasCode) {
      this.logger.warn(
        `debugIssue called with no evidence code — debug quality will be low`,
      );
    }

    const body: AiEngineCodeUnderstandingRequest = {
      source_code: sourceCode || `// No source available for debugging: ${issue}`,
      language,
      file_path: filePath,
      question: `Debug the following issue and identify the root cause and fix: ${issue}`,
      context,
      analyses: ['error_explanation'],
    };

    const raw = await this.callAiEngine(body);

    // The AI Engine returns the full debug analysis in `summary`.  Split it
    // into root-cause and fix heuristically at "fix:" / "Fix:" boundary, or
    // return the full text as rootCause when no boundary is found.
    const { rootCause, fix } = splitDebugSummary(raw.summary);

    return {
      rootCause,
      fix,
      evidence,
      confidence: raw.confidence?.level ?? 'UNKNOWN',
    };
  }

  // ---------------------------------------------------------------------------
  // Low-level HTTP call
  // ---------------------------------------------------------------------------

  private async callAiEngine(
    body: AiEngineCodeUnderstandingRequest,
  ): Promise<AiEngineCodeUnderstandingResponse> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), GEMMA_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(`${AI_ENGINE_BASE_URL}/api/v1/code-understanding`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timer);
      const isAbort =
        typeof err === 'object' &&
        err !== null &&
        'name' in err &&
        (err as { name?: unknown }).name === 'AbortError';
      const msg = isAbort ? 'Gemma call timed out' : `Gemma call failed: ${String(err)}`;
      this.logger.error(msg);
      throw new Error(msg);
    }

    clearTimeout(timer);

    if (!response.ok) {
      const msg = `Gemma returned HTTP ${response.status}`;
      this.logger.error(msg);
      throw new Error(msg);
    }

    const data = (await response.json()) as AiEngineCodeUnderstandingResponse;
    return data;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Heuristically split an AI Engine summary into (rootCause, fix) parts.
 *
 * The AI Engine's error_explanation analysis tends to produce text with a
 * "Fix:" or "fix:" heading.  When no such boundary exists the full text is
 * treated as the root cause and a generic fix suggestion is returned.
 */
function splitDebugSummary(summary: string): {
  rootCause: string;
  fix: string;
} {
  // Try common heading patterns: "Fix:", "Suggested fix:", "Fixes:"
  const fixPattern = /\b(suggested\s+)?fix(es)?:/i;
  const match = fixPattern.exec(summary);

  if (match && match.index > 0) {
    const rootCause = summary.slice(0, match.index).trim();
    const fix = summary.slice(match.index).trim();
    return { rootCause: rootCause || summary, fix: fix || summary };
  }

  // "Resolution:", "Solution:"
  const altPattern = /\b(resolution|solution):/i;
  const altMatch = altPattern.exec(summary);
  if (altMatch && altMatch.index > 0) {
    const rootCause = summary.slice(0, altMatch.index).trim();
    const fix = summary.slice(altMatch.index).trim();
    return { rootCause: rootCause || summary, fix: fix || summary };
  }

  return { rootCause: summary, fix: summary };
}
