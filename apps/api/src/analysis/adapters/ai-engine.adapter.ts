import {
  BadGatewayException,
  BadRequestException,
  GatewayTimeoutException,
  Injectable,
  InternalServerErrorException,
  ServiceUnavailableException,
} from '@nestjs/common';
import type {
  AnalysisRequest,
  IAnalysisProvider,
} from '../interfaces/analysis-provider.interface.js';
import type {
  AnalysisResult,
  ConfidenceMetadata,
  Evidence,
} from '../models/analysis-result.model.js';
import type { AiEngineRequestContract } from '../contracts/ai-engine-request.contract.js';
import type {
  AiEngineEvidenceItem,
  AiEngineResponseContract,
} from '../contracts/ai-engine-response.contract.js';
import {
  AiEngineClient,
  AiEngineClientError,
  type AiEngineClientErrorCode,
} from './ai-engine.client.js';

// ---------------------------------------------------------------------------
// Evidence source_type → Evidence.kind mapping
//
// 'syntax'  — evidence from raw syntactic / structural code analysis (AST, tokens)
// 'semantic' — evidence from meaning/behaviour analysis (types, scope, data flow)
// 'ai'      — AI/LLM reasoning, or any source_type not matching the above categories
//
// The raw source_type is always preserved in the structured Evidence fields
// so no information is lost regardless of which kind bucket is chosen.

const SYNTAX_PATTERNS = /syntax|ast|token|grammar|parse/i;
const SEMANTIC_PATTERNS = /semantic|type|scope|flow|symbol|reference/i;

function mapSourceTypeToKind(
  sourceType: string,
): Evidence['kind'] {
  if (SYNTAX_PATTERNS.test(sourceType)) return 'syntax';
  if (SEMANTIC_PATTERNS.test(sourceType)) return 'semantic';
  return 'ai';
}

// ---------------------------------------------------------------------------
// Confidence level normalisation

type NormalisedLevel = ConfidenceMetadata['level'];

function normaliseLevel(raw: string): NormalisedLevel {
  switch (raw.toUpperCase()) {
    case 'HIGH':
      return 'high';
    case 'MEDIUM':
      return 'medium';
    case 'LOW':
      return 'low';
    case 'UNKNOWN':
    default:
      return 'unknown';
  }
}

// ---------------------------------------------------------------------------
// Error code → NestJS HTTP exception mapping

const NESTJS_EXCEPTION_MAP: Record<
  AiEngineClientErrorCode,
  () => never
> = {
  validation_error: () => {
    throw new BadRequestException('Invalid analysis request.');
  },
  provider_unavailable: () => {
    throw new ServiceUnavailableException(
      'Analysis service is temporarily unavailable.',
    );
  },
  provider_timeout: () => {
    throw new GatewayTimeoutException('Analysis service timed out.');
  },
  provider_error: () => {
    throw new BadGatewayException('Analysis provider returned an error.');
  },
  internal_error: () => {
    throw new InternalServerErrorException(
      'Analysis service encountered an internal error.',
    );
  },
  network_error: () => {
    throw new ServiceUnavailableException('Analysis service is unreachable.');
  },
  timeout: () => {
    throw new GatewayTimeoutException('Analysis request timed out.');
  },
};

// ---------------------------------------------------------------------------

@Injectable()
export class AiEngineAdapterProvider implements IAnalysisProvider {
  constructor(private readonly client: AiEngineClient) {}

  async analyzeCode(request: AnalysisRequest): Promise<AnalysisResult> {
    const aiRequest = this.toAiEngineRequest(request);

    let aiResponse: AiEngineResponseContract;
    try {
      aiResponse = await this.client.post(aiRequest);
    } catch (err: unknown) {
      if (err instanceof AiEngineClientError) {
        NESTJS_EXCEPTION_MAP[err.code]();
      }
      // Unexpected non-client error — re-throw as internal
      throw new InternalServerErrorException(
        'An unexpected error occurred during analysis.',
      );
    }

    return this.fromAiEngineResponse(aiResponse, request);
  }

  // ---------------------------------------------------------------------------
  // Request mapping

  private toAiEngineRequest(
    request: AnalysisRequest,
  ): AiEngineRequestContract {
    return {
      source_code: request.code,
      language: request.language,
      file_path: request.filePath ?? null,
      question: null, // not in AnalysisRequest yet; AI Engine accepts null
      context: request.context ?? null,
      analyses: [], // not in AnalysisRequest yet; AI Engine accepts empty array
    };
  }

  // ---------------------------------------------------------------------------
  // Response mapping

  private fromAiEngineResponse(
    response: AiEngineResponseContract,
    request: AnalysisRequest,
  ): AnalysisResult {
    return {
      requestId: request.requestId,
      language: response.metadata.language || request.language,
      symbols: [],
      relationships: [],
      summary: response.summary,
      confidence: this.mapConfidence(response),
      evidence: response.confidence.evidence.map((item) =>
        this.mapEvidenceItem(item),
      ),
      analysedAt: new Date().toISOString(),
    };
  }

  private mapConfidence(response: AiEngineResponseContract): ConfidenceMetadata {
    return {
      // The AI Engine provides no numeric score — score is absent, not zero.
      // 'unknown' level is preserved as-is; no heuristic number is manufactured.
      score: undefined,
      level: normaliseLevel(response.confidence.level),
      model: undefined, // AI Engine does not expose model identity in its response
      reasoning: response.confidence.notes || undefined,
    };
  }

  private mapEvidenceItem(item: AiEngineEvidenceItem): Evidence {
    // Build a human-readable detail string that includes all available fields
    // so no information is lost even when the consumer only reads `detail`.
    const locationParts: string[] = [];
    if (item.file_path) locationParts.push(`file:${item.file_path}`);
    if (item.line_start !== null && item.line_end !== null) {
      locationParts.push(`lines:${item.line_start}-${item.line_end}`);
    } else if (item.line_start !== null) {
      locationParts.push(`line:${item.line_start}`);
    }
    if (item.chunk_id) locationParts.push(`chunk:${item.chunk_id}`);

    const detail =
      locationParts.length > 0
        ? `${item.description} [${locationParts.join(', ')}]`
        : item.description;

    return {
      kind: mapSourceTypeToKind(item.source_type),
      detail,
      // Preserve all structured fields so consumers can access them directly
      // without parsing the detail string.
      sourceType: item.source_type,
      filePath: item.file_path ?? undefined,
      lineStart: item.line_start ?? undefined,
      lineEnd: item.line_end ?? undefined,
      chunkId: item.chunk_id ?? undefined,
    };
  }
}
