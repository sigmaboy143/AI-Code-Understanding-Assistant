import { CodeRelationship } from './code-relationship.model.js';
import { CodeSymbol } from './code-symbol.model.js';

export interface Evidence {
  kind: 'syntax' | 'semantic' | 'ai';
  detail: string;
}

export interface ConfidenceMetadata {
  score: number;
  level: 'low' | 'medium' | 'high';
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
