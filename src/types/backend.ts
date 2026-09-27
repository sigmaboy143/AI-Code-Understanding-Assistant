// ─────────────────────────────────────────────────────────────────────────────
// Member 1 backend wire contract — transcribed from
// feature/member1-backend-core-intelligence @ afda26c
//
// These types are a MIRROR, not an invention. Every shape below was read
// directly out of apps/api/src/... on that commit. Nothing here may be changed
// to suit the frontend: if the backend contract moves, this file is what tells
// us the frontend no longer matches.
//
// Source of truth per type:
//   AnalysisResult            apps/api/src/analysis/models/analysis-result.model.ts
//   ConfidenceMetadata        apps/api/src/analysis/models/analysis-result.model.ts
//   BackendEvidence           apps/api/src/analysis/models/analysis-result.model.ts
//   CodeSymbol / SymbolKind   apps/api/src/analysis/models/code-symbol.model.ts
//   CodeRelationship          apps/api/src/analysis/models/code-relationship.model.ts
//   AnalyzeCodeDto            apps/api/src/analysis/dto/analyze-code.dto.ts
//   AnalyzeFileDto            apps/api/src/analysis/dto/analyze-file.dto.ts
//   ExplanationResponseDto    apps/api/src/explanations/dto/explanation-response.dto.ts
//   ExplainCodeDto            apps/api/src/explanations/dto/explain-code.dto.ts
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Categorical confidence level as the backend models it.
 *
 * This is deliberately wider than the UI's three-state `ConfidenceLevel`. The
 * backend retains `low`/`medium`/`high` for providers that predate the AI
 * Engine's CONFIRMED/INFERRED/UNKNOWN contract. All six must be tolerated on
 * the way in; the adapter decides what the UI is allowed to display.
 */
export type BackendConfidenceLevel =
  | "low"
  | "medium"
  | "high"
  | "confirmed"
  | "inferred"
  | "unknown";

export interface BackendConfidenceMetadata {
  /**
   * Numeric score 0–1. Optional: absence means "not provided", which is NOT the
   * same as zero. The AI Engine produces no numeric score at all.
   */
  score?: number;
  level: BackendConfidenceLevel;
  model?: string;
  reasoning?: string;
}

/**
 * Backend evidence.
 *
 * `kind` and `sourceType` are both present and both meaningful: `kind` is the
 * backend's taxonomy, `sourceType` is the AI Engine's own `source_type` value
 * carried through verbatim. Neither may be collapsed into the other.
 */
export interface BackendEvidence {
  kind: string;
  detail: string;
  sourceType?: string;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  chunkId?: string;
}

export type BackendSymbolKind =
  | "function"
  | "class"
  | "method"
  | "variable"
  | "interface"
  | "type"
  | "enum"
  | "module";

export interface BackendSymbolLocation {
  filePath: string;
  startLine: number;
  endLine: number;
  startColumn: number;
  endColumn: number;
}

export interface BackendCodeSymbol {
  id: string;
  name: string;
  kind: BackendSymbolKind;
  location: BackendSymbolLocation;
  signature?: string;
  documentation?: string;
}

export type BackendRelationshipKind =
  | "calls"
  | "imports"
  | "extends"
  | "implements"
  | "references"
  | "instantiates";

export interface BackendCodeRelationship {
  id: string;
  fromSymbolId: string;
  toSymbolId: string;
  kind: BackendRelationshipKind;
  filePath: string;
  line: number;
}

/**
 * The real `POST /analysis/code` and `POST /analysis/file` response body.
 *
 * Note what is NOT here. The shape carries no `referencedSymbols`, no
 * `generatedAt` and no `detailed`. It has `symbols`/`relationships` and — note
 * the British spelling — `analysedAt`. The adapter must read these names
 * exactly; sending a request for `referencedSymbols` would be reading a
 * different endpoint's contract.
 */
export interface BackendAnalysisResult {
  requestId: string;
  language: string;
  symbols: BackendCodeSymbol[];
  relationships: BackendCodeRelationship[];
  summary?: string;
  confidence: BackendConfidenceMetadata;
  evidence: BackendEvidence[];
  analysedAt: string;
}

/** The real `POST /explanations` response body. */
export interface BackendExplanationResponse {
  requestId: string;
  summary: string;
  detailed?: string;
  confidence: BackendConfidenceMetadata;
  referencedSymbols: BackendCodeSymbol[];
  generatedAt: string;
}

/**
 * `POST /analysis/code` request body.
 *
 * Every key here is whitelisted by AnalyzeCodeDto. The backend runs
 * `whitelist: true` + `forbidNonWhitelisted: true`, so adding a key here that
 * the DTO does not declare produces a 400 rather than being ignored.
 */
export interface AnalyzeCodeBody {
  language: string;
  code: string;
  filePath?: string;
  context?: string;
}

/** `POST /analysis/file` request body. `filePath` is required here, unlike above. */
export interface AnalyzeFileBody {
  language: string;
  filePath: string;
  code: string;
  context?: string;
}

/** `POST /explanations` request body. */
export interface ExplainCodeBody {
  language: string;
  code: string;
  filePath?: string;
  startLine?: number;
  endLine?: number;
  detailLevel?: "brief" | "standard" | "detailed";
}

/** Mirrors `@MaxLength(100000)` on `code` in both analyze DTOs. */
export const BACKEND_MAX_CODE_LENGTH = 100000;

/**
 * Inbound/outbound correlation header implemented by Member 1's
 * CorrelationIdMiddleware. A supplied ID matching `^[A-Za-z0-9._~-]{1,128}$` is
 * honoured; anything else is replaced with a fresh UUID. The response header is
 * always present, including on a 400.
 */
export const X_REQUEST_ID_HEADER = "X-Request-Id";
export const X_REQUEST_ID_PATTERN = /^[A-Za-z0-9._~-]{1,128}$/;
