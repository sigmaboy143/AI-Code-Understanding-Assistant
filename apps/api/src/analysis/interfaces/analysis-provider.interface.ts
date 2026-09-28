import { AnalysisResult } from '../models/analysis-result.model.js';

/**
 * Injection token for the analysis provider.
 * Register a concrete implementation against this token in AnalysisModule.
 * Future phases will introduce an adapter that communicates with the external
 * AI Engine; AnalysisService and AnalysisController remain unchanged.
 */
export const ANALYSIS_PROVIDER = 'ANALYSIS_PROVIDER';

export interface AnalysisRequest {
  requestId: string;
  language: string;
  code: string;
  filePath?: string;
  context?: string;
}

/**
 * Contract that every analysis provider must satisfy.
 * Phase 1 is satisfied by NullAnalysisProvider (stub).
 * Later phases will introduce an AiEngineAdapterProvider that calls the
 * external AI Engine without changing this interface or its consumers.
 */
export interface IAnalysisProvider {
  analyzeCode(request: AnalysisRequest): Promise<AnalysisResult>;
}
