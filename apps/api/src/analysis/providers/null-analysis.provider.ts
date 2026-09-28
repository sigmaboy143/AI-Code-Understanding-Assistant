import { Injectable } from '@nestjs/common';
import {
  AnalysisRequest,
  IAnalysisProvider,
} from '../interfaces/analysis-provider.interface.js';
import {
  AnalysisResult,
  Evidence,
} from '../models/analysis-result.model.js';

/**
 * Stub provider used while no real AI Engine adapter is wired.
 * Returns a valid, well-typed empty AnalysisResult that clearly indicates
 * no analysis has been performed. Confidence score is 0 and evidence
 * explicitly records that this is an unimplemented stub.
 */
@Injectable()
export class NullAnalysisProvider implements IAnalysisProvider {
  async analyzeCode(request: AnalysisRequest): Promise<AnalysisResult> {
    const stubEvidence: Evidence = {
      kind: 'semantic',
      detail:
        'No analysis provider is configured. ' +
        'NullAnalysisProvider returns an empty stub result. ' +
        'Wire a real IAnalysisProvider implementation to enable analysis.',
    };

    return {
      requestId: request.requestId,
      language: request.language,
      symbols: [],
      relationships: [],
      summary: undefined,
      confidence: {
        score: 0,
        level: 'low',
        model: 'none',
        reasoning: 'Analysis provider not yet implemented.',
      },
      evidence: [stubEvidence],
      analysedAt: new Date().toISOString(),
    };
  }
}
