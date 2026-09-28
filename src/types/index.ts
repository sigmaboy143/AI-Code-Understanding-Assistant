// ─────────────────────────────────────────────────────────────────────────────
// Shared types used across the extension host and webview
// ─────────────────────────────────────────────────────────────────────────────

export type ExplanationMode = "beginner" | "intermediate" | "advanced";

export type ConfidenceLevel = "confirmed" | "inferred" | "unknown";

export type PanelTab =
  | "explain"
  | "why"
  | "relations"
  | "dataflow"
  | "history"
  | "impact"
  | "tests"
  | "debug"
  | "architecture"
  | "search"
  | "conversation";

// ── Code context sent to the backend ────────────────────────────────────────

export interface CodeContext {
  repositoryId?: string;
  file: string;
  selectedText?: string;
  startLine?: number;
  endLine?: number;
  language?: string;
  workspaceRoot?: string;
}

// ── Evidence attached to AI responses ────────────────────────────────────────

/**
 * Evidence item as the UI consumes it.
 *
 * `file`/`lines`/`description` are the original display-oriented fields and stay
 * exactly as they were, because the mock service and EvidenceList already read
 * them. The fields below them are additive and carry the backend's real
 * evidence model through without lossy conversion: `kind` is the backend
 * taxonomy, `sourceType` is the AI Engine's verbatim `source_type`. Neither is
 * derivable from the other, so both are kept.
 *
 * `commit`/`pr`/`issue` are populated only by mock data. The backend exposes no
 * git evidence today, so a real response will leave them undefined rather than
 * invent them.
 */
export interface Evidence {
  file: string;
  lines?: [number, number];
  commit?: string;
  pr?: string;
  issue?: string;
  description?: string;

  /** Backend `Evidence.kind`, preserved verbatim. */
  kind?: string;
  /** AI Engine `source_type`, preserved verbatim and distinct from `kind`. */
  sourceType?: string;
  /** Structured location, kept alongside the display-oriented `file`/`lines`. */
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  /** Retrieval chunk identifier, when the evidence came from a retrieved chunk. */
  chunkId?: string;
  /** Backend's human-readable `detail` string. */
  detail?: string;
}

/** Provenance of a response, so the UI never implies mock data is real. */
export type ResultSource = "backend" | "mock";

/**
 * A backend feature the panel can display but the backend cannot currently
 * serve. The real backend at afda26c exposes no HTTP route for these, so in real
 * mode they resolve to a capability notice instead of a fabricated request.
 */
export type BackendCapability =
  | "why"
  | "dataflow"
  | "history"
  | "impact"
  | "tests"
  | "debug"
  | "architecture"
  | "search"
  | "conversation";

// ── Explanation response ─────────────────────────────────────────────────────

/**
 * The model the Explain tab renders.
 *
 * The original what/how/why trio is retained because the UI still has those
 * sections, but the backend does not produce three separate fields — it
 * returns one `summary` (and, on /explanations, an optional `detailed`). The
 * adapter therefore populates `what` from `summary` and leaves `how`/`why`
 * empty unless real backend text exists for them. Mock mode still fills all
 * three, as before.
 *
 * The fields below the divider are the real backend payload, kept intact so
 * nothing is lost: `requestId` for correlation, `analysedAt`/`generatedAt` for
 * timing, the raw confidence metadata including `reasoning` and an optional
 * numeric `score`, and the structured `symbols`/`relationships`.
 */
export interface ExplanationResponse {
  what: string;
  how: string;
  why: string;
  where?: string;
  related?: string[];
  tests?: string[];
  history?: string;
  impact?: string;
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
  mode: ExplanationMode;

  // ── Real backend payload (populated when source === "backend") ────────────
  source?: ResultSource;
  /** Backend correlation ID, echoed into the UI for support/debugging. */
  requestId?: string;
  /** Backend timestamp field. Spelled as the backend spells it. */
  analysedAt?: string;
  /** Present only on POST /explanations, which has a `generatedAt` field. */
  generatedAt?: string;
  detailed?: string;
  confidenceMeta?: {
    level: string;
    score?: number;
    model?: string;
    reasoning?: string;
  };
  symbols?: UiSymbol[];
  relationships?: UiRelationship[];
}

/** A backend `CodeSymbol` in the shape the UI displays it. */
export interface UiSymbol {
  id: string;
  name: string;
  kind: string;
  filePath?: string;
  startLine?: number;
  endLine?: number;
  signature?: string;
  documentation?: string;
}

/** A backend `CodeRelationship` in the shape the UI displays it. */
export interface UiRelationship {
  id: string;
  fromSymbolId: string;
  toSymbolId: string;
  kind: string;
  filePath?: string;
  line?: number;
}

// ── Why / History response ───────────────────────────────────────────────────

export interface WhyResponse {
  reason: string;
  context: string;
  commits?: CommitInfo[];
  prs?: PrInfo[];
  issues?: string[];
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

export interface CommitInfo {
  hash: string;
  message: string;
  author: string;
  date: string;
  diff?: string;
}

export interface PrInfo {
  number: number;
  title: string;
  description?: string;
  url?: string;
}

// ── Relationship node ────────────────────────────────────────────────────────

export interface RelationNode {
  id: string;
  label: string;
  /**
   * `symbol` is the honest type for a node synthesised from a backend
   * relationship whose target symbol could not be resolved to a known kind.
   * Guessing `function` or `class` from a relationship alone would invent a
   * fact the backend never stated.
   */
  type: "file" | "function" | "class" | "api" | "database" | "service" | "symbol";
  file?: string;
  line?: number;
}

export interface RelationEdge {
  from: string;
  to: string;
  label?: string;
}

export interface RelationsResponse {
  nodes: RelationNode[];
  edges: RelationEdge[];
  confidence: ConfidenceLevel;
  evidence?: Evidence[];

  // ── Real backend payload (populated when source === "backend") ────────────
  source?: ResultSource;
  requestId?: string;
  /** Raw relationships exactly as GET /relationships returned them. */
  relationships?: UiRelationship[];
}

// ── Data-flow step ───────────────────────────────────────────────────────────

export interface DataFlowStep {
  id: string;
  label: string;
  type: "input" | "function" | "service" | "api" | "database" | "output";
  file?: string;
  line?: number;
  description?: string;
}

export interface DataFlowResponse {
  steps: DataFlowStep[];
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

// ── History response ─────────────────────────────────────────────────────────

export interface HistoryResponse {
  commits: CommitInfo[];
  summary: string;
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

// ── Impact response ──────────────────────────────────────────────────────────

export interface ImpactNode {
  id: string;
  label: string;
  type: "direct" | "indirect" | "test" | "api";
  file?: string;
}

export interface ImpactResponse {
  root: string;
  nodes: ImpactNode[];
  summary: string;
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

// ── Test response ────────────────────────────────────────────────────────────

export interface TestInfo {
  file: string;
  name: string;
  description?: string;
  lines?: [number, number];
  coverage?: number;
}

export interface TestsResponse {
  tests: TestInfo[];
  summary: string;
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

// ── Debug response ───────────────────────────────────────────────────────────

export interface DebugResponse {
  error: string;
  rootCause: string;
  callChain: string[];
  relatedCode: string[];
  recentChanges: CommitInfo[];
  possibleCauses: Array<{ cause: string; confidence: ConfidenceLevel }>;
  confidence: ConfidenceLevel;
  evidence?: Evidence[];
}

// ── Architecture response ────────────────────────────────────────────────────

export interface ArchitectureLayer {
  id: string;
  label: string;
  components: string[];
  description?: string;
}

export interface ArchitectureResponse {
  layers: ArchitectureLayer[];
  description: string;
  confidence: ConfidenceLevel;
}

// ── Messages exchanged between extension host and webview ───────────────────

export type ExtensionToWebviewMessage =
  | { type: "setContext"; payload: CodeContext }
  | { type: "setTab"; payload: { tab: PanelTab } }
  | { type: "setExplanationMode"; payload: { mode: ExplanationMode } }
  | { type: "loading"; payload: { tab: PanelTab } }
  | { type: "error"; payload: { tab: PanelTab; message: string } }
  /**
   * The backend exposes no HTTP route for this feature. Sent instead of a
   * result or a hard error so the tab can say "not currently available" rather
   * than implying a failed analysis.
   */
  | { type: "capability"; payload: { tab: PanelTab; capability: BackendCapability; message: string } }
  | { type: "explanationResult"; payload: ExplanationResponse }
  | { type: "whyResult"; payload: WhyResponse }
  | { type: "relationsResult"; payload: RelationsResponse }
  | { type: "dataflowResult"; payload: DataFlowResponse }
  | { type: "historyResult"; payload: HistoryResponse }
  | { type: "impactResult"; payload: ImpactResponse }
  | { type: "testsResult"; payload: TestsResponse }
  | { type: "debugResult"; payload: DebugResponse }
  | { type: "architectureResult"; payload: ArchitectureResponse }
  | { type: "useMock"; payload: { value: boolean } };

export type WebviewToExtensionMessage =
  | { type: "ready" }
  | { type: "requestExplain"; payload: { context: CodeContext; mode: ExplanationMode } }
  | { type: "requestWhy"; payload: { context: CodeContext } }
  | { type: "requestRelations"; payload: { context: CodeContext } }
  | { type: "requestDataFlow"; payload: { context: CodeContext } }
  | { type: "requestHistory"; payload: { context: CodeContext } }
  | { type: "requestImpact"; payload: { context: CodeContext } }
  | { type: "requestTests"; payload: { context: CodeContext } }
  | { type: "requestDebug"; payload: { context: CodeContext; error?: string } }
  | { type: "requestArchitecture"; payload: { repositoryId?: string } }
  | { type: "navigate"; payload: { file: string; line?: number } }
  | { type: "askQuestion"; payload: { question: string; context: CodeContext } };
