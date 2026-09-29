import type {
  CodeContext,
  ConfidenceLevel,
  Evidence,
  ExplanationMode,
  ExplanationResponse,
  RelationsResponse,
  UiRelationship,
  UiSymbol,
} from "../types";
import type {
  AnalyzeCodeBody,
  AnalyzeFileBody,
  BackendAnalysisResult,
  BackendCodeRelationship,
  BackendCodeSymbol,
  BackendConfidenceMetadata,
  BackendEvidence,
  BackendExplanationResponse,
  ExplainCodeBody,
} from "../types/backend";

// ─────────────────────────────────────────────────────────────────────────────
// This module is intentionally free of any `vscode` import.
//
// It is the only place that knows both the backend wire contract and the UI
// model, which makes it the single seam between the two, and makes it
// unit-testable without booting the extension host. Anything that needs the
// editor API belongs in contextCollector, not here.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Raised when a feature has no backend HTTP route at all.
 *
 * This is deliberately distinct from a request failure. Nothing was attempted
 * and nothing broke; the capability simply does not exist yet. The UI shows a
 * "not currently available" notice for this rather than a red error, so a
 * missing backend feature is never mistaken for a broken backend.
 */
export class BackendCapabilityError extends Error {
  readonly capability: string;

  constructor(capability: string, message: string) {
    super(message);
    this.name = "BackendCapabilityError";
    this.capability = capability;
  }
}

/** Raised for any failed backend call, carrying a message safe to show a user. */
export class BackendRequestError extends Error {
  readonly status?: number;
  readonly requestId?: string;

  constructor(message: string, status?: number, requestId?: string) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
    this.requestId = requestId;
  }
}

/** True when a thrown value is a "backend has no such feature" signal. */
export function isBackendCapabilityError(err: unknown): err is BackendCapabilityError {
  return err instanceof BackendCapabilityError;
}

// ─────────────────────────────────────────────────────────────────────────────
// Request bodies
//
// The backend ValidationPipe runs with `whitelist: true` AND
// `forbidNonWhitelisted: true`, so an undeclared key is a 400, not a silently
// dropped field. These builders therefore emit only keys the corresponding DTO
// declares, and omit optional keys entirely rather than sending null.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Falls back to a non-blank language id.
 *
 * AnalyzeCodeDto requires `language` to match /\S/, so an empty or whitespace
 * `languageId` (untitled buffers, some plaintext/untitled documents) would be a
 * guaranteed 400. `plaintext` is the id VS Code itself assigns such documents.
 */
function requireLanguage(ctx: CodeContext): string {
  const language = ctx.language?.trim();
  return language && language.length > 0 ? language : "plaintext";
}

/** POST /analysis/code body. */
export function buildAnalyzeCodeBody(ctx: CodeContext, code: string): AnalyzeCodeBody {
  const body: AnalyzeCodeBody = {
    language: requireLanguage(ctx),
    code,
  };

  if (ctx.file) {
    body.filePath = ctx.file;
  }
  // `context` is only sent when the caller actually has one. There is no
  // legitimate value to invent here, and the backend maps an absent context to
  // null on the way to the AI Engine.
  if (ctx.workspaceRoot) {
    body.context = `Workspace root: ${ctx.workspaceRoot}`;
  }

  return body;
}

/** POST /analysis/file body. `filePath` is required by AnalyzeFileDto. */
export function buildAnalyzeFileBody(ctx: CodeContext, code: string): AnalyzeFileBody {
  const body: AnalyzeFileBody = {
    language: requireLanguage(ctx),
    // AnalyzeFileDto uses @IsNotEmpty on filePath, so it may not be omitted.
    filePath: ctx.file || "untitled",
    code,
  };

  if (ctx.workspaceRoot) {
    body.context = `Workspace root: ${ctx.workspaceRoot}`;
  }

  return body;
}

/** POST /explanations body. */
export function buildExplainCodeBody(
  ctx: CodeContext,
  code: string,
  detailLevel: "brief" | "standard" | "detailed" = "standard"
): ExplainCodeBody {
  const body: ExplainCodeBody = {
    language: requireLanguage(ctx),
    code,
    detailLevel,
  };

  if (ctx.file) {
    body.filePath = ctx.file;
  }
  if (typeof ctx.startLine === "number") {
    body.startLine = ctx.startLine;
  }
  if (typeof ctx.endLine === "number") {
    body.endLine = ctx.endLine;
  }

  return body;
}

/**
 * GET /relationships query parameters.
 *
 * The route takes exactly these two. There is no POST form of it, and the
 * relationship payload is real — but the backend service currently resolves to
 * an empty array, which is a backend state, not a frontend one.
 */
export function buildRelationshipsQuery(ctx: CodeContext): { filePath: string; language: string } {
  return {
    filePath: ctx.file || "untitled",
    language: requireLanguage(ctx),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Confidence
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Maps backend confidence onto the badge's three states.
 *
 * confirmed / inferred / unknown are carried across by identity: they are the
 * AI Engine's own states and collapsing them would assert a strength it never
 * claimed.
 *
 * low / medium / high are the backend's legacy vocabulary, kept for providers
 * that predate the three-state contract. They are translated into the
 * equivalent badge state rather than discarded. This is a change of words, not
 * of meaning — but the translation is deliberately conservative, so an
 * unrecognised or missing level can only ever become "unknown", never stronger.
 *
 * The untouched level is always preserved separately in `confidenceMeta.level`,
 * so nothing is lost either way.
 */
export function mapConfidenceLevel(
  meta: BackendConfidenceMetadata | undefined | null
): ConfidenceLevel {
  const level = meta?.level;
  if (typeof level !== "string") {
    return "unknown";
  }

  switch (level.toLowerCase()) {
    case "confirmed":
      return "confirmed";
    case "inferred":
      return "inferred";
    case "high":
      return "confirmed";
    case "medium":
      return "inferred";
    case "low":
    case "unknown":
    default:
      return "unknown";
  }
}

function mapConfidenceMeta(
  meta: BackendConfidenceMetadata | undefined | null
): ExplanationResponse["confidenceMeta"] {
  if (!meta) {
    return { level: "unknown" };
  }
  const mapped: NonNullable<ExplanationResponse["confidenceMeta"]> = {
    level: typeof meta.level === "string" ? meta.level : "unknown",
  };
  // `score` stays undefined when the backend did not provide one. The AI Engine
  // produces no numeric score; absence means "not provided" and must never be
  // rendered as 0%.
  if (typeof meta.score === "number" && Number.isFinite(meta.score)) {
    mapped.score = meta.score;
  }
  if (typeof meta.model === "string" && meta.model.length > 0) {
    mapped.model = meta.model;
  }
  if (typeof meta.reasoning === "string" && meta.reasoning.length > 0) {
    mapped.reasoning = meta.reasoning;
  }
  return mapped;
}

// ─────────────────────────────────────────────────────────────────────────────
// Evidence
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Adapts backend evidence to the UI shape without losing structured fields.
 *
 * `file` and `lines` are filled from the structured `filePath`/`lineStart`/
 * `lineEnd` so the existing navigation link keeps working, while `kind`,
 * `sourceType`, `chunkId` and `detail` are carried verbatim. No commit, PR or
 * issue field is ever populated: the backend exposes no git evidence today.
 */
export function mapEvidence(items: BackendEvidence[] | undefined | null): Evidence[] {
  if (!Array.isArray(items)) {
    return [];
  }

  return items.map((item) => {
    const mapped: Evidence = {
      file: item.filePath ?? "",
    };

    if (item.kind !== undefined) {
      mapped.kind = item.kind;
    }
    if (item.sourceType !== undefined) {
      mapped.sourceType = item.sourceType;
    }
    if (item.filePath !== undefined) {
      mapped.filePath = item.filePath;
    }
    if (typeof item.lineStart === "number") {
      mapped.lineStart = item.lineStart;
    }
    if (typeof item.lineEnd === "number") {
      mapped.lineEnd = item.lineEnd;
    }
    if (item.chunkId !== undefined) {
      mapped.chunkId = item.chunkId;
    }
    if (typeof item.detail === "string" && item.detail.length > 0) {
      mapped.detail = item.detail;
    }

    const hasRange =
      typeof item.lineStart === "number" && typeof item.lineEnd === "number";
    if (hasRange) {
      mapped.lines = [item.lineStart as number, item.lineEnd as number];
    } else if (typeof item.lineStart === "number") {
      mapped.lines = [item.lineStart, item.lineStart];
    }

    // The badge row shows `description`; the backend calls the same idea
    // `detail`. Reusing the field avoids a second, parallel prop in the UI
    // while the original `detail` value stays available too.
    if (typeof item.detail === "string" && item.detail.length > 0) {
      mapped.description = item.detail;
    }

    return mapped;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Symbols and relationships
// ─────────────────────────────────────────────────────────────────────────────

function mapSymbol(symbol: BackendCodeSymbol): UiSymbol {
  const mapped: UiSymbol = {
    id: symbol.id,
    name: symbol.name,
    kind: symbol.kind,
  };
  if (symbol.location?.filePath) {
    mapped.filePath = symbol.location.filePath;
  }
  if (typeof symbol.location?.startLine === "number") {
    mapped.startLine = symbol.location.startLine;
  }
  if (typeof symbol.location?.endLine === "number") {
    mapped.endLine = symbol.location.endLine;
  }
  if (symbol.signature) {
    mapped.signature = symbol.signature;
  }
  if (symbol.documentation) {
    mapped.documentation = symbol.documentation;
  }
  return mapped;
}

export function mapSymbols(
  symbols: BackendCodeSymbol[] | undefined | null
): UiSymbol[] {
  if (!Array.isArray(symbols)) {
    return [];
  }
  return symbols.map(mapSymbol);
}

function mapRelationship(relationship: BackendCodeRelationship): UiRelationship {
  const mapped: UiRelationship = {
    id: relationship.id,
    fromSymbolId: relationship.fromSymbolId,
    toSymbolId: relationship.toSymbolId,
    kind: relationship.kind,
  };
  if (relationship.filePath) {
    mapped.filePath = relationship.filePath;
  }
  if (typeof relationship.line === "number") {
    mapped.line = relationship.line;
  }
  return mapped;
}

export function mapRelationships(
  relationships: BackendCodeRelationship[] | undefined | null
): UiRelationship[] {
  if (!Array.isArray(relationships)) {
    return [];
  }
  return relationships.map(mapRelationship);
}

// ─────────────────────────────────────────────────────────────────────────────
// AnalysisResult → ExplanationResponse
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Adapts a real `AnalysisResult` into the model the Explain tab renders.
 *
 * The backend returns a single `summary`; it does not return separate
 * what/how/why prose. Rather than split one paragraph three ways and imply the
 * model made three separate findings, the summary is surfaced as `what` and the
 * `how`/`why` fields are left empty for the UI to render as "not provided".
 * Fabricating a rationale the AI Engine did not produce is the one thing this
 * adapter must never do — the whole point of the confidence and evidence
 * fields is to let a reader see what is actually supported.
 */
export function mapAnalysisResult(
  result: BackendAnalysisResult,
  mode: ExplanationMode,
  ctx?: CodeContext
): ExplanationResponse {
  const response: ExplanationResponse = {
    what: typeof result.summary === "string" ? result.summary : "",
    how: "",
    why: "",
    confidence: mapConfidenceLevel(result.confidence),
    confidenceMeta: mapConfidenceMeta(result.confidence),
    evidence: mapEvidence(result.evidence),
    mode,
    source: "backend",
  };

  if (result.requestId) {
    response.requestId = result.requestId;
  }
  if (result.analysedAt) {
    response.analysedAt = result.analysedAt;
  }

  // `where` describes the analysed location. The backend does not echo a
  // location back, so this is reconstructed from the request that was sent —
  // a statement about what was analysed, not a claim the AI Engine made.
  const location = describeLocation(ctx, result.language);
  if (location) {
    response.where = location;
  }

  const symbols = mapSymbols(result.symbols);
  if (symbols.length > 0) {
    response.symbols = symbols;
  }
  const relationships = mapRelationships(result.relationships);
  if (relationships.length > 0) {
    response.relationships = relationships;
  }

  return response;
}

function describeLocation(ctx: CodeContext | undefined, language: string | undefined): string | undefined {
  const parts: string[] = [];
  if (ctx?.file) {
    if (typeof ctx.startLine === "number" && typeof ctx.endLine === "number") {
      parts.push(`${ctx.file}:${ctx.startLine}-${ctx.endLine}`);
    } else {
      parts.push(ctx.file);
    }
  }
  if (language) {
    parts.push(language);
  }
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

/** Adapts the real `POST /explanations` response. Shares the model above. */
export function mapExplanationsResult(
  result: BackendExplanationResponse,
  mode: ExplanationMode
): ExplanationResponse {
  const response: ExplanationResponse = {
    what: typeof result.summary === "string" ? result.summary : "",
    how: typeof result.detailed === "string" ? result.detailed : "",
    why: "",
    confidence: mapConfidenceLevel(result.confidence),
    confidenceMeta: mapConfidenceMeta(result.confidence),
    evidence: [],
    mode,
    source: "backend",
  };

  if (result.requestId) {
    response.requestId = result.requestId;
  }
  if (result.generatedAt) {
    response.generatedAt = result.generatedAt;
  }
  if (typeof result.detailed === "string" && result.detailed.length > 0) {
    response.detailed = result.detailed;
  }

  const symbols = mapSymbols(result.referencedSymbols);
  if (symbols.length > 0) {
    response.symbols = symbols;
  }

  return response;
}

/**
 * Builds the Relations-tab model from a real `CodeRelationship[]`.
 *
 * GET /relationships returns relationships only — no symbol names, no symbol
 * kinds. Nodes are therefore synthesised from the referenced symbol IDs and
 * typed as `symbol`, which says only "this is a symbol ID we could not
 * resolve". Passing `symbolsById` (available when the relationships came from
 * an /analysis/* response) upgrades labels and kinds to real values.
 */
export function mapRelationsResponse(
  relationships: BackendCodeRelationship[] | undefined | null,
  options: { symbolsById?: Map<string, BackendCodeSymbol> } = {}
): RelationsResponse {
  const relations = mapRelationships(relationships);
  const lookup = options.symbolsById;

  const nodes = new Map<string, { id: string; label: string; type: RelationsResponse["nodes"][number]["type"]; file?: string; line?: number }>();
  const edges: RelationsResponse["edges"] = [];

  for (const relation of relations) {
    for (const symbolId of [relation.fromSymbolId, relation.toSymbolId]) {
      if (nodes.has(symbolId)) {
        continue;
      }
      const symbol = lookup?.get(symbolId);
      nodes.set(symbolId, {
        id: symbolId,
        label: symbol?.name ?? symbolId,
        type: symbol?.kind === "function" || symbol?.kind === "method" ? "function" : "symbol",
        ...(symbol?.location?.filePath ? { file: symbol.location.filePath } : {}),
        ...(typeof symbol?.location?.startLine === "number"
          ? { line: symbol.location.startLine }
          : {}),
      });
    }

    edges.push({
      from: relation.fromSymbolId,
      to: relation.toSymbolId,
      label: relation.kind,
    });
  }

  return {
    nodes: [...nodes.values()],
    edges,
    // GET /relationships returns no confidence of its own. Reporting
    // "unknown" is the honest state: no provider asserted a strength.
    confidence: "unknown",
    evidence: [],
    source: "backend",
    relationships: relations,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Errors
// ─────────────────────────────────────────────────────────────────────────────

interface ErrorLike {
  message?: unknown;
  code?: unknown;
  response?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Pulls the backend's own message out of a NestJS error body.
 *
 * NestJS validation failures arrive as `{ message: string | string[] }`, so the
 * array form is joined rather than rendered as "[object Object]".
 */
function extractBackendMessage(body: unknown): string | undefined {
  if (!isRecord(body)) {
    return undefined;
  }
  const message = body.message;
  if (typeof message === "string" && message.trim().length > 0) {
    return message.trim();
  }
  if (Array.isArray(message)) {
    const parts = message
      .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
      .map((entry) => entry.trim());
    if (parts.length > 0) {
      return parts.join("; ");
    }
  }
  const error = body.error;
  if (typeof error === "string" && error.trim().length > 0 && message === undefined) {
    return error.trim();
  }
  return undefined;
}

function describeStatus(status: number): string {
  switch (status) {
    case 400:
      return "The backend rejected the request as invalid.";
    case 401:
      return "The backend requires authentication, which is not configured for this extension.";
    case 403:
      return "The backend refused this request.";
    case 404:
      return "The backend has no endpoint at that address.";
    case 408:
      return "The backend request timed out.";
    case 502:
      return "The backend could not reach the AI provider.";
    case 503:
      return "The backend or the AI provider is unavailable.";
    case 504:
      return "The AI provider did not respond in time.";
    default:
      return status >= 500
        ? "The backend reported an internal error."
        : "The backend rejected the request.";
  }
}

/**
 * Turns any thrown value into a message that is safe and useful to show.
 *
 * Axios internals (the request object, the full config, the stack of adapter
 * frames) are never surfaced. What is surfaced is the status class, the
 * backend's own message when it sent one, and the correlation ID so the user
 * can quote it when reporting a problem.
 */
export function describeBackendError(err: unknown, requestId?: string): string {
  const suffix = requestId ? ` (request ${requestId})` : "";
  const asError = isRecord(err) ? (err as ErrorLike) : undefined;

  if (isBackendCapabilityError(err)) {
    return err.message;
  }

  if (asError && isRecord(asError.response)) {
    const response = asError.response;
    const status = typeof response.status === "number" ? response.status : undefined;
    const backendMessage = extractBackendMessage(response.data);
    const base = status ? `${describeStatus(status)} (HTTP ${status})` : describeBackendFallback(asError);
    return `${base}${backendMessage ? ` — ${backendMessage}` : ""}${suffix}`;
  }

  if (asError?.code === "ECONNABORTED" || asError?.code === "ETIMEDOUT") {
    return `The backend did not respond in time.${suffix}`;
  }

  return `${describeBackendFallback(asError)}${suffix}`;
}

function describeBackendFallback(err: ErrorLike | undefined): string {
  const code = typeof err?.code === "string" ? err.code : undefined;
  if (code === "ECONNREFUSED") {
    return "Could not reach the backend. Check that it is running and that aicode.backendUrl is correct.";
  }
  if (code === "ENOTFOUND" || code === "EAI_AGAIN") {
    return "The backend host could not be resolved. Check aicode.backendUrl.";
  }
  if (typeof err?.message === "string" && err.message.trim().length > 0) {
    return `The request failed: ${err.message.trim()}`;
  }
  return "The request to the backend failed.";
}
