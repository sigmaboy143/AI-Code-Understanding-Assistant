/**
 * Authoritative contract defined by Prakash's hub integration.
 * Do NOT modify field names or signatures — Prakash's integration layer
 * depends on this exact shape.
 */

export interface LLMResponse {
  answer: string;
  reasoning?: string;
  evidence?: Array<{
    file: string;
    symbol: string;
    startLine: number;
    endLine: number;
  }>;
  dependencyPath?: string[];
  rootCause?: string;
  fix?: string;
}

/**
 * Context object produced by the retrieval adapter and passed to the Gemma adapter.
 * Evidence items from Yashwanth's EvidenceItem DTO include a `code` field used
 * internally for grounded reasoning but not returned in LLMResponse.
 */
export interface RetrievalContext {
  evidence?: Array<{
    file: string;
    symbol?: string;
    startLine?: number;
    endLine?: number;
    code?: string;
    [key: string]: unknown;
  }>;
  dependencyPath?: string[];
  [key: string]: unknown;
}

export abstract class IGemmaAdapter {
  abstract generateAnswer(query: string, context: RetrievalContext): Promise<LLMResponse>;
  abstract debugIssue(issue: string, context: RetrievalContext): Promise<LLMResponse>;
}
