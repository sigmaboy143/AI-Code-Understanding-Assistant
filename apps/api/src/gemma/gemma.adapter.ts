import { Injectable, Logger } from '@nestjs/common';
import { GemmaService } from './service/gemma.service.js';
import { IGemmaAdapter, LLMResponse, RetrievalContext } from './gemma-adapter.interface.js';
import type { EvidenceItem } from './dto/evidence-item.dto.js';

/**
 * Real GemmaAdapter — satisfies Prakash's IGemmaAdapter contract by delegating
 * to Yashwanth's GemmaService (Gemma 4 / GEMINI_API_KEY).
 *
 * generateAnswer  → evidence-grounded answer using GemmaService.analyzeWithEvidence
 * debugIssue      → evidence-grounded diagnosis with rootCause + fix extraction
 *
 * Field mapping:
 *   internal suggestedFix   → public LLMResponse.fix
 *   internal confidence      kept internal (not part of public LLMResponse)
 *   internal insufficientEvidence → represented via answer text + no rootCause/fix
 */
@Injectable()
export class GemmaAdapter implements IGemmaAdapter {
  private readonly logger = new Logger(GemmaAdapter.name);

  constructor(private readonly gemmaService: GemmaService) {}

  // ─── generateAnswer ────────────────────────────────────────────────────────

  async generateAnswer(query: string, context: RetrievalContext): Promise<LLMResponse> {
    this.logger.log(`generateAnswer called for query: "${query}"`);

    const { evidenceItems, dependencyPath } = this.extractContext(context);

    // Delegate to the existing evidence-grounded reasoning layer
    const result = await this.gemmaService.analyzeWithEvidence(
      query,
      evidenceItems,
      dependencyPath,
    );

    // Strip the confidence bracket from reasoning if present
    const reasoning = this.extractReasoning(result.answer);

    return {
      answer: result.answer,
      reasoning,
      evidence: this.mapEvidence(context),
      dependencyPath: dependencyPath.length > 0 ? dependencyPath : undefined,
    };
  }

  // ─── debugIssue ────────────────────────────────────────────────────────────

  async debugIssue(issue: string, context: RetrievalContext): Promise<LLMResponse> {
    this.logger.log(`debugIssue called for issue: "${issue}"`);

    const { evidenceItems, dependencyPath } = this.extractContext(context);

    // Build a debug-specific prompt that requests structured rootCause + fix output
    const debugQuestion = this.buildDebugQuestion(issue);

    const result = await this.gemmaService.analyzeWithEvidence(
      debugQuestion,
      evidenceItems,
      dependencyPath,
    );

    // If insufficient evidence, return an honest answer with no fabricated rootCause/fix
    if (result.insufficientEvidence) {
      return {
        answer: result.answer,
        evidence: this.mapEvidence(context),
        dependencyPath: dependencyPath.length > 0 ? dependencyPath : undefined,
      };
    }

    // Parse structured rootCause and fix/suggestedFix from the model response
    const { rootCause, fix, reasoning } = this.parseDebugResponse(result.answer);

    const response: LLMResponse = {
      answer: result.answer,
      reasoning,
      evidence: this.mapEvidence(context),
      dependencyPath: dependencyPath.length > 0 ? dependencyPath : undefined,
    };

    // Only add rootCause/fix when the model provided evidence-grounded values
    if (rootCause) {
      response.rootCause = rootCause;
    }
    if (fix) {
      // Map internal suggestedFix → public contract field "fix"
      response.fix = fix;
    }

    return response;
  }

  // ─── Internal helpers ──────────────────────────────────────────────────────

  /**
   * Normalize the retrieval context into the shapes GemmaService expects.
   */
  private extractContext(context: RetrievalContext): {
    evidenceItems: EvidenceItem[];
    dependencyPath: string[];
  } {
    const raw = context?.evidence ?? [];
    const dependencyPath = context?.dependencyPath ?? [];

    const evidenceItems: EvidenceItem[] = raw.map((e) => ({
      file: e.file ?? 'unknown',
      symbol: e.symbol ?? undefined,
      startLine: typeof e.startLine === 'number' ? e.startLine : undefined,
      endLine: typeof e.endLine === 'number' ? e.endLine : undefined,
      // GemmaService uses `code` for grounded reasoning; fall back to a
      // brief file/symbol description when no code snippet is supplied.
      code: typeof e.code === 'string' && e.code.length > 0
        ? e.code
        : `File: ${e.file}${e.symbol ? `, Symbol: ${e.symbol}` : ''}` +
          (typeof e.startLine === 'number' ? `, lines ${e.startLine}–${e.endLine ?? e.startLine}` : ''),
    }));

    return { evidenceItems, dependencyPath };
  }

  /**
   * Map raw context evidence to the public LLMResponse Evidence shape.
   * Evidence returned must correspond to supplied evidence — no fabrication.
   */
  private mapEvidence(
    context: RetrievalContext,
  ): LLMResponse['evidence'] {
    const raw = context?.evidence ?? [];
    if (raw.length === 0) return undefined;

    return raw.map((e) => ({
      file: e.file ?? 'unknown',
      symbol: e.symbol ?? '',
      startLine: typeof e.startLine === 'number' ? e.startLine : 0,
      endLine: typeof e.endLine === 'number' ? e.endLine : 0,
    }));
  }

  /**
   * Extracts the reasoning portion of a Gemma answer (text before a confidence
   * bracket, or the full answer when no bracket is present).
   */
  private extractReasoning(answer: string): string | undefined {
    if (!answer) return undefined;
    const bracketIdx = answer.search(/\[(high|medium|low)\]/i);
    return bracketIdx > 0 ? answer.slice(0, bracketIdx).trim() : answer.trim();
  }

  /**
   * Wraps the issue in a structured debug prompt so the model returns
   * clearly labelled ROOT_CAUSE and SUGGESTED_FIX sections.
   */
  private buildDebugQuestion(issue: string): string {
    return `Debug the following issue using only the supplied evidence.

ISSUE: ${issue}

Provide your response in this exact structure:
ROOT_CAUSE: <one-sentence root cause based only on evidence, or "Cannot determine from evidence">
SUGGESTED_FIX: <concrete remediation based only on evidence, or "Cannot determine from evidence">
EXPLANATION: <detailed explanation grounded in the evidence>

Rules:
- rootCause and fix MUST be supported by the evidence.
- Do NOT fabricate implementation details.
- If evidence is insufficient write exactly "Cannot determine from evidence" for that field.`;
  }

  /**
   * Parses the structured debug response for ROOT_CAUSE, SUGGESTED_FIX, and
   * the remainder as reasoning.  Maps SUGGESTED_FIX → public field "fix".
   */
  private parseDebugResponse(text: string): {
    rootCause?: string;
    fix?: string;
    reasoning?: string;
  } {
    if (!text) return {};

    const rootCauseMatch = text.match(/ROOT_CAUSE:\s*(.+?)(?=\n|SUGGESTED_FIX:|$)/is);
    const fixMatch = text.match(/SUGGESTED_FIX:\s*(.+?)(?=\n|EXPLANATION:|$)/is);
    const explanationMatch = text.match(/EXPLANATION:\s*([\s\S]+?)(?=\n\[(?:high|medium|low)\]|$)/i);

    const rootCause = rootCauseMatch?.[1]?.trim();
    // Map SUGGESTED_FIX → public "fix" field per Prakash contract
    const fix = fixMatch?.[1]?.trim();
    const reasoning = explanationMatch?.[1]?.trim() || text.trim();

    const INSUFFICIENT = 'cannot determine from evidence';

    return {
      rootCause: rootCause && rootCause.toLowerCase() !== INSUFFICIENT ? rootCause : undefined,
      fix: fix && fix.toLowerCase() !== INSUFFICIENT ? fix : undefined,
      reasoning,
    };
  }
}
