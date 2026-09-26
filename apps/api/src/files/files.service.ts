import { Injectable } from '@nestjs/common';
import {
  AnalysisResult,
} from '../analysis/models/analysis-result.model.js';

@Injectable()
export class FilesService {
  getFileAnalysis(fileId: string): Promise<AnalysisResult> {
    return Promise.resolve({
      requestId: fileId,
      language: 'unknown',
      symbols: [],
      relationships: [],
      summary: undefined,
      confidence: {
        score: 0,
        level: 'low',
        model: 'none',
        reasoning: 'File analysis not yet implemented.',
      },
      evidence: [
        {
          kind: 'semantic',
          detail:
            'File analysis is a stub. No analysis provider has processed this file.',
        },
      ],
      analysedAt: new Date().toISOString(),
    });
  }
}
