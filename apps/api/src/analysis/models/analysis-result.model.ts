import { CodeRelationship } from './code-relationship.model.js';
import { CodeSymbol } from './code-symbol.model.js';

export interface Evidence {
  kind: 'syntax' | 'semantic' | 'ai';
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
   * 'unknown' is used when the provider explicitly signals unverified output
   * (e.g. the AI Engine returns UNKNOWN for free-text responses).
   */
  level: 'low' | 'medium' | 'high' | 'unknown';
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
