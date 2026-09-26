/**
 * Exact response shapes from the AI Engine.
 * Field names are as specified by Member 3's FastAPI contract.
 */

export interface AiEngineEvidenceItem {
  source_type: string;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  chunk_id: string | null;
  description: string;
}

export interface AiEngineConfidence {
  /** Raw level string from the AI Engine — e.g. 'LOW', 'MEDIUM', 'HIGH', 'UNKNOWN'. */
  level: string;
  evidence: AiEngineEvidenceItem[];
  notes: string;
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
