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
// Evidence source_type → Evidence.kind
//
// The AI Engine's `source_type` (its `EvidenceSourceType` enum) is the
// authoritative statement of where evidence came from, and every value it can
// emit is already a member of the `EvidenceKind` union. It is therefore carried
// through by identity.
//
// It is deliberately NOT reinterpreted as `syntax` / `semantic` / `ai`.
// Collapsing it required guessing: nothing in the AI Engine contract says
// `source_code` is "syntax" or `documentation` is "semantic". Under the previous
// regex mapping every real AI Engine source type fell through to `ai`, which
// both destroyed the distinction and contradicted the rule that evidence must
// not be blindly classified as `ai`.
//
// `sourceType` on the Evidence item continues to carry the raw value verbatim.

// ---------------------------------------------------------------------------
// Confidence level normalisation
//
// The AI Engine's `ConfidenceLevel` enum is CONFIRMED | INFERRED | UNKNOWN.
// These are preserved as distinct states. Mapping CONFIRMED to 'high' or
// INFERRED to 'medium' would assert a strength the AI Engine never claimed.
//
// HIGH/MEDIUM/LOW are retained because providers that predate the three-state
// AI Engine contract emit them, and they remain part of ConfidenceMetadata.

type NormalisedLevel = ConfidenceMetadata['level'];

function normaliseLevel(raw: string): NormalisedLevel {
  switch (raw.toUpperCase()) {
    case 'CONFIRMED':
      return 'confirmed';
    case 'INFERRED':
      return 'inferred';
    case 'UNKNOWN':
      return 'unknown';
    // Retained for providers that predate the three-state AI Engine contract.
    case 'HIGH':
      return 'high';
    case 'MEDIUM':
      return 'medium';
    case 'LOW':
      return 'low';
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
      // `analyses` is intentionally omitted. AnalysisRequest carries no explicit
      // analysis selection, and CodeUnderstandingRequest.analyses has
      // `min_length=1`, so sending `[]` would be rejected with 422. Omitting the
      // key lets the AI Engine apply its own default of all five AnalysisType
      // values. JSON.stringify drops the undefined property, so the key is
      // absent from the wire body rather than present-and-null.
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
      // The AI Engine provides no numeric score — the contract has no such
      // field, and its confidence model is explicitly non-numeric. `score` stays
      // absent, which means "not provided", never zero. No heuristic number is
      // manufactured.
      score: undefined,
      // CONFIRMED / INFERRED / UNKNOWN are preserved as distinct levels. See
      // normaliseLevel above for why no strength conversion is applied.
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

    // `description` is nullable in the AI Engine contract. When it is absent the
    // location summary is used on its own rather than stringifying `null`.
    const description = item.description ?? '';
    const detail =
      locationParts.length > 0
        ? `${description} [${locationParts.join(', ')}]`
        : description;

    return {
      // Identity mapping: the AI Engine's source_type is already a member of
      // the EvidenceKind union. No semantic reinterpretation, no fabrication.
      kind: item.source_type,
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
