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

export interface Evidence {
  file: string;
  lines?: [number, number];
  commit?: string;
  pr?: string;
  issue?: string;
  description?: string;
}

// ── Explanation response ─────────────────────────────────────────────────────

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
  type: "file" | "function" | "class" | "api" | "database" | "service";
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
