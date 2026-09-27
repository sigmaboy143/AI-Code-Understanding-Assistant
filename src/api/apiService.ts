import * as vscode from "vscode";
import axios from "axios";
import { randomUUID } from "crypto";
import {
  CodeContext,
  ExplanationMode,
  ExplanationResponse,
  WhyResponse,
  RelationsResponse,
  DataFlowResponse,
  HistoryResponse,
  ImpactResponse,
  TestsResponse,
  DebugResponse,
  ArchitectureResponse,
  BackendCapability,
} from "../types";
import type {
  BackendAnalysisResult,
  BackendCodeRelationship,
  BackendExplanationResponse,
} from "../types/backend";
import { X_REQUEST_ID_HEADER, X_REQUEST_ID_PATTERN } from "../types/backend";
import {
  BackendCapabilityError,
  BackendRequestError,
  buildAnalyzeCodeBody,
  buildAnalyzeFileBody,
  buildExplainCodeBody,
  buildRelationshipsQuery,
  describeBackendError,
  mapAnalysisResult,
  mapExplanationsResult,
  mapRelationsResponse,
} from "./analysisAdapter";
import * as mock from "./mockService";

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

function backendUrl(): string {
  const configured = vscode.workspace
    .getConfiguration("aicode")
    .get<string>("backendUrl", "http://localhost:3000")
    .trim();
  return configured.replace(/\/+$/, "");
}

export function isMockMode(): boolean {
  return vscode.workspace
    .getConfiguration("aicode")
    .get<boolean>("useMockData", true);
}

/** Message shown for a feature the backend genuinely has no route for. */
function capabilityMessage(capability: string, label: string): string {
  return (
    `${label} is not available: the backend does not expose an HTTP endpoint for ` +
    `"${capability}". Enable mock mode (aicode.useMockData) to explore the demo UI.`
  );
}

/**
 * The features the backend has no route for, as of Member 1 @ afda26c.
 *
 * Every entry here was confirmed by reading the controller. The
 * `tests`, `conversations`, `documentation`, `onboarding`, `auth`, `users`,
 * `organizations`, `projects` and `repositories` controllers are declared but
 * carry no route handler at all, and impact / debugging / architecture / git /
 * dataflow / history exist only as injectable services with no controller.
 */
const UNSUPPORTED: Record<string, string> = {
  why: "Why does this exist?",
  dataflow: "Trace Data Flow",
  history: "Git history",
  impact: "Impact analysis",
  tests: "Related tests",
  debug: "Debug / diagnose errors",
  architecture: "Architecture overview",
  // `search` and `conversation` are listed for completeness: they are the same
  // class of gap, but they are webview-only tabs with no command and no entry
  // point here, so nothing below calls notAvailable() with them. Each tab gates
  // itself on aicode.useMockData and shows the capability notice directly.
  search: "Natural-language search",
  conversation: "Ask about this code",
};

function notAvailable(capability: BackendCapability): never {
  const label = UNSUPPORTED[capability] ?? capability;
  throw new BackendCapabilityError(capability, capabilityMessage(capability, label));
}

// ─────────────────────────────────────────────────────────────────────────────
// Transport
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A correlation ID for outbound requests.
 *
 * Member 1's CorrelationIdMiddleware honours an inbound `X-Request-Id` matching
 * `^[A-Za-z0-9._~-]{1,128}$` and always echoes one back, so the header is a
 * real part of the contract rather than something invented for tracing. A
 * random UUID always satisfies the allowlist.
 */
function newRequestId(): string {
  const candidate = randomUUID();
  return X_REQUEST_ID_PATTERN.test(candidate) ? candidate : randomUUID();
}

function readResponseRequestId(headers: unknown): string | undefined {
  if (typeof headers !== "object" || headers === null) {
    return undefined;
  }
  const bag = headers as Record<string, unknown>;
  const raw = bag[X_REQUEST_ID_HEADER.toLowerCase()] ?? bag[X_REQUEST_ID_HEADER];
  return typeof raw === "string" && raw.length > 0 ? raw : undefined;
}

interface CallOptions {
  timeout?: number;
  requestId?: string;
}

async function callBackend<T>(
  method: "post" | "get",
  path: string,
  body: object | undefined,
  options: CallOptions = {}
): Promise<{ data: T; requestId: string }> {
  const url = `${backendUrl()}${path}`;
  const requestId = options.requestId ?? newRequestId();
  const config = {
    timeout: options.timeout ?? 30000,
    headers: { [X_REQUEST_ID_HEADER]: requestId },
    // A 201 is the documented success status for the analysis routes. Axios
    // already treats every 2xx as success, so this only documents intent.
    validateStatus: (status: number) => status >= 200 && status < 300,
  };

  let response;
  try {
    response =
      method === "post"
        ? await axios.post<T>(url, body, config)
        : await axios.get<T>(url, config);
  } catch (err) {
    // A correlation ID from the failing response is preferred over the one we
    // sent: the backend may have replaced ours, and on a 400 the middleware sets
    // the header before validation rejects the body.
    const serverId = extractErrorRequestId(err) ?? requestId;
    throw new BackendRequestError(describeBackendError(err, serverId), extractStatus(err), serverId);
  }

  const resolved = readResponseRequestId(response.headers) ?? requestId;

  if (response.data === undefined || response.data === null || response.data === "") {
    throw new BackendRequestError(
      "The backend returned an empty response body.",
      response.status,
      resolved
    );
  }

  return { data: response.data, requestId: resolved };
}

function extractErrorRequestId(err: unknown): string | undefined {
  if (typeof err !== "object" || err === null) {
    return undefined;
  }
  const response = (err as { response?: unknown }).response;
  if (typeof response !== "object" || response === null) {
    return undefined;
  }
  return readResponseRequestId((response as { headers?: unknown }).headers);
}

function extractStatus(err: unknown): number | undefined {
  if (typeof err !== "object" || err === null) {
    return undefined;
  }
  const response = (err as { response?: unknown }).response;
  if (typeof response !== "object" || response === null) {
    return undefined;
  }
  const status = (response as { status?: unknown }).status;
  return typeof status === "number" ? status : undefined;
}

// ─────────────────────────────────────────────────────────────────────────────
// Real backend endpoints
// ─────────────────────────────────────────────────────────────────────────────

/**
 * POST /analysis/code — analyses the currently selected code.
 *
 * `code` is passed explicitly rather than read from the context, because the
 * text to analyse is decided by the caller (selection vs whole file) and the
 * document is only reachable from the extension host.
 */
export async function requestAnalysis(
  ctx: CodeContext,
  code: string,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  const { data } = await callBackend<BackendAnalysisResult>(
    "post",
    "/analysis/code",
    buildAnalyzeCodeBody(ctx, code)
  );
  return mapAnalysisResult(data, mode, ctx);
}

/**
 * POST /analysis/file — analyses the complete file.
 *
 * `code` must be the whole document text. Sending a selection here would still
 * return a 201, but it would be a 201 for the wrong thing.
 */
export async function requestFileAnalysis(
  ctx: CodeContext,
  code: string,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  const { data } = await callBackend<BackendAnalysisResult>(
    "post",
    "/analysis/file",
    buildAnalyzeFileBody(ctx, code)
  );
  return mapAnalysisResult(data, mode, ctx);
}

/** POST /explanations — the dedicated explanation route. */
export async function requestExplanation(
  ctx: CodeContext,
  code: string,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  const { data } = await callBackend<BackendExplanationResponse>(
    "post",
    "/explanations",
    buildExplainCodeBody(ctx, code)
  );
  return mapExplanationsResult(data, mode);
}

/** GET /relationships?filePath&language — the real relationships route. */
export async function requestRelationships(
  ctx: CodeContext
): Promise<RelationsResponse> {
  const query = buildRelationshipsQuery(ctx);
  const search = new URLSearchParams({
    filePath: query.filePath,
    language: query.language,
  });

  const { data } = await callBackend<BackendCodeRelationship[]>(
    "get",
    `/relationships?${search.toString()}`,
    undefined
  );

  return mapRelationsResponse(Array.isArray(data) ? data : []);
}

// ─────────────────────────────────────────────────────────────────────────────
// Public API — mock mode stays exactly as it was
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Explain the selected code.
 *
 * In real mode this targets POST /analysis/code, which is the route whose
 * contract matches what the panel needs. Mock mode is untouched.
 */
export async function explainCode(
  ctx: CodeContext,
  code: string,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  if (isMockMode()) {
    return mock.mockExplain(ctx, mode);
  }
  return requestAnalysis(ctx, code, mode);
}

/** Explain the entire active file via POST /analysis/file. */
export async function explainFile(
  ctx: CodeContext,
  code: string,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  if (isMockMode()) {
    return mock.mockExplain(ctx, mode);
  }
  return requestFileAnalysis(ctx, code, mode);
}

/** GET /relationships in real mode; mock graph in mock mode. */
export async function getRelations(ctx: CodeContext): Promise<RelationsResponse> {
  if (isMockMode()) {
    return mock.mockRelations(ctx);
  }
  return requestRelationships(ctx);
}

// ── Features the backend does not implement yet ──────────────────────────────
//
// Each of these previously called a URL that does not exist. In mock mode they
// keep returning demo data; in real mode they raise a capability error so the UI
// can say the feature is unavailable rather than reporting a failed analysis.

export async function explainWhy(ctx: CodeContext): Promise<WhyResponse> {
  if (isMockMode()) {
    return mock.mockWhy(ctx);
  }
  return notAvailable("why");
}

export async function traceDataFlow(ctx: CodeContext): Promise<DataFlowResponse> {
  if (isMockMode()) {
    return mock.mockDataFlow(ctx);
  }
  return notAvailable("dataflow");
}

export async function getHistory(ctx: CodeContext): Promise<HistoryResponse> {
  if (isMockMode()) {
    return mock.mockHistory(ctx);
  }
  return notAvailable("history");
}

export async function analyzeImpact(ctx: CodeContext): Promise<ImpactResponse> {
  if (isMockMode()) {
    return mock.mockImpact(ctx);
  }
  return notAvailable("impact");
}

export async function findTests(ctx: CodeContext): Promise<TestsResponse> {
  if (isMockMode()) {
    return mock.mockTests(ctx);
  }
  return notAvailable("tests");
}

export async function debugError(ctx: CodeContext, error?: string): Promise<DebugResponse> {
  if (isMockMode()) {
    return mock.mockDebug(ctx, error);
  }
  return notAvailable("debug");
}

export async function getArchitecture(): Promise<ArchitectureResponse> {
  if (isMockMode()) {
    return mock.mockArchitecture();
  }
  return notAvailable("architecture");
}

export type { BackendCapability };
