import { ConfidenceMetadata } from '../../analysis/models/analysis-result.model.js';
import { CodeSymbol } from '../../analysis/models/code-symbol.model.js';

export interface ExplanationResponseDto {
  requestId: string;
  summary: string;
  detailed?: string;
  confidence: ConfidenceMetadata;
  referencedSymbols: CodeSymbol[];
  generatedAt: string;
}
