/**
 * Exact response shapes from the AI Engine.
 * Field names are as specified by Member 3's FastAPI contract
 * (feature/member3-ai @ 532f035, app/evidence/models.py and
 * app/schemas/code_understanding.py).
 */

/**
 * Exact `EvidenceSourceType` values the AI Engine can emit.
 *
 * `test` and `git_commit` are defined by the AI Engine but documented as
 * reserved and never auto-populated, so they are declared to keep the
 * vocabulary faithful and are never produced by this backend.
 */
export type AiEngineEvidenceSourceType =
  | 'source_code'
  | 'retrieved_chunk'
  | 'file'
  | 'documentation'
  | 'test'
  | 'git_commit';

/**
 * Exact `ConfidenceLevel` values the AI Engine can emit.
 * There is no HIGH/MEDIUM/LOW confidence level in this contract.
 */
export type AiEngineConfidenceLevel = 'CONFIRMED' | 'INFERRED' | 'UNKNOWN';

export interface AiEngineEvidenceItem {
  source_type: AiEngineEvidenceSourceType;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  chunk_id: string | null;
  description: string | null;
}

export interface AiEngineConfidence {
  /** Raw level from the AI Engine's `ConfidenceLevel` enum. */
  level: AiEngineConfidenceLevel;
  evidence: AiEngineEvidenceItem[];
  notes: string | null;
}

export interface AiEngineMetadata {
  language: string;
  file_path: string | null;
  analyses: string[];
}

export interface AiEngineResponseContract {
  summary: string;
  metadata: AiEngineMetadata;
  confidence: AiEngineConfidence;
  explanation: object | null;
  structure: object | null;
  dependencies: object | null;
  improvements: object | null;
}

/**
 * Error envelope returned by the AI Engine on 4xx/5xx responses.
 */
export interface AiEngineErrorEnvelope {
  error: {
    code: string;
    message: string;
  };
}
