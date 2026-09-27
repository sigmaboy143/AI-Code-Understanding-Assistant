import { CodeRelationship } from './code-relationship.model.js';
import { CodeSymbol } from './code-symbol.model.js';

/**
 * Evidence classification.
 *
 * The first three values are the original backend-internal taxonomy, still
 * produced by providers that do not originate their evidence from the AI
 * Engine (NullAnalysisProvider, FilesService).
 *
 * The remaining values are the AI Engine's own `EvidenceSourceType` enum
 * (feature/member3-ai @ 532f035, app/evidence/models.py). The AI Engine's
 * `source_type` is the authoritative statement of where evidence came from, so
 * it is carried through verbatim instead of being reinterpreted as
 * `syntax`/`semantic`/`ai`. Reinterpreting it would invent meaning the AI
 * Engine never asserted — for example treating `source_code` as `syntax` or
 * `documentation` as `semantic` is a guess, not a mapping.
 *
 * `test` and `git_commit` are defined by the AI Engine but are documented as
 * reserved and never auto-populated. They are listed so the vocabulary is
 * complete, not because the backend may fabricate them.
 */
export type EvidenceKind =
  | 'syntax'
  | 'semantic'
  | 'ai'
  | 'source_code'
  | 'retrieved_chunk'
  | 'file'
  | 'documentation'
  | 'test'
  | 'git_commit';

export interface Evidence {
  kind: EvidenceKind;
  /** Human-readable summary of this evidence item. */
  detail: string;
  /**
   * Structured fields populated when evidence originates from the AI Engine.
   * All are optional so existing Evidence construction (NullAnalysisProvider etc.)
   * requires no changes.
   */
  sourceType?: string;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  chunkId?: string;
}

export interface ConfidenceMetadata {
  /**
   * Numeric confidence score (0–1) when supplied by the provider.
   * Optional because not all providers produce a numeric score.
   * Absence means the score was not provided — it does not mean zero confidence.
   */
  score?: number;
  /**
   * Categorical confidence level.
   *
   * 'confirmed' and 'inferred' are the AI Engine's own `ConfidenceLevel` states
   * (feature/member3-ai @ 532f035): CONFIRMED means directly supported by
   * evidence, INFERRED means reasoned but not established, UNKNOWN means
   * insufficient evidence. These are preserved rather than collapsed, because
   * collapsing INFERRED into 'medium' or CONFIRMED into 'high' would assert a
   * strength the AI Engine never claimed.
   *
   * 'low' | 'medium' | 'high' are retained for providers that predate the
   * three-state AI Engine contract. 'unknown' is used when the provider
   * explicitly signals unverified output (the AI Engine returns UNKNOWN for
   * free-text responses).
   */
  level: 'low' | 'medium' | 'high' | 'confirmed' | 'inferred' | 'unknown';
  model?: string;
  reasoning?: string;
}

export interface AnalysisResult {
  requestId: string;
  language: string;
  symbols: CodeSymbol[];
  relationships: CodeRelationship[];
  summary?: string;
  confidence: ConfidenceMetadata;
  evidence: Evidence[];
  analysedAt: string;
}
