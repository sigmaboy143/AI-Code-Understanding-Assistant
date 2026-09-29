import { create } from "zustand";
import type {
  CodeContext,
  PanelTab,
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
} from "../types";

export type LoadingState = "idle" | "loading" | "success" | "error";

/**
 * Why a tab is showing nothing.
 *
 * `unavailable` is not an error state. It means the backend exposes no HTTP
 * endpoint for the feature, so there is no result and no failure to report. It
 * is kept separate from "error" so a missing backend capability is never
 * presented as a broken request.
 */
export type TabAvailability = "available" | "unavailable";

interface TabState<T> {
  status: LoadingState;
  data?: T;
  error?: string;
  /** Set when the backend has no endpoint for this feature. */
  unavailable?: boolean;
  /** Human-readable explanation shown when `unavailable` is true. */
  unavailableMessage?: string;
}

export interface AppState {
  // Context
  codeContext: CodeContext | null;
  activeTab: PanelTab;
  explanationMode: ExplanationMode;
  useMock: boolean;

  // Conversation
  conversationHistory: Array<{ role: "user" | "assistant"; content: string }>;

  // Tab data
  explanation: TabState<ExplanationResponse>;
  why: TabState<WhyResponse>;
  relations: TabState<RelationsResponse>;
  dataflow: TabState<DataFlowResponse>;
  history: TabState<HistoryResponse>;
  impact: TabState<ImpactResponse>;
  tests: TabState<TestsResponse>;
  debug: TabState<DebugResponse>;
  architecture: TabState<ArchitectureResponse>;

  // Actions
  setCodeContext: (ctx: CodeContext) => void;
  setActiveTab: (tab: PanelTab) => void;
  setExplanationMode: (mode: ExplanationMode) => void;
  setUseMock: (v: boolean) => void;
  setLoading: (tab: PanelTab) => void;
  setError: (tab: PanelTab, message: string) => void;
  setUnavailable: (tab: PanelTab, message: string) => void;
  setExplanation: (data: ExplanationResponse) => void;
  setWhy: (data: WhyResponse) => void;
  setRelations: (data: RelationsResponse) => void;
  setDataFlow: (data: DataFlowResponse) => void;
  setHistory: (data: HistoryResponse) => void;
  setImpact: (data: ImpactResponse) => void;
  setTests: (data: TestsResponse) => void;
  setDebug: (data: DebugResponse) => void;
  setArchitecture: (data: ArchitectureResponse) => void;
  addConversationMessage: (role: "user" | "assistant", content: string) => void;
  clearConversation: () => void;
}

/**
 * Maps a PanelTab value (used in messages) to the corresponding store state key.
 * "explain" → "explanation" because the store uses "explanation" as the key
 * to match the full type name (ExplanationResponse), while the tab ID is "explain".
 */
function tabKey(tab: PanelTab): string {
  return tab === "explain" ? "explanation" : tab;
}

export const useAppStore = create<AppState>((set) => ({
  codeContext: null,
  activeTab: "explain",
  explanationMode: "intermediate",
  useMock: true,

  conversationHistory: [],

  explanation: { status: "idle" },
  why: { status: "idle" },
  relations: { status: "idle" },
  dataflow: { status: "idle" },
  history: { status: "idle" },
  impact: { status: "idle" },
  tests: { status: "idle" },
  debug: { status: "idle" },
  architecture: { status: "idle" },

  setCodeContext: (ctx) => set({ codeContext: ctx }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setExplanationMode: (mode) => set({ explanationMode: mode }),
  setUseMock: (v) => set({ useMock: v }),

  setLoading: (tab) => set((s) => ({ ...s, [tabKey(tab)]: { status: "loading" } })),
  setError: (tab, message) =>
    set((s) => ({ ...s, [tabKey(tab)]: { status: "error", error: message } })),
  setUnavailable: (tab, message) =>
    set((s) => ({
      ...s,
      [tabKey(tab)]: { status: "idle", unavailable: true, unavailableMessage: message },
    })),

  setExplanation: (data) =>
    set({ explanation: { status: "success", data } }),
  setWhy: (data) => set({ why: { status: "success", data } }),
  setRelations: (data) => set({ relations: { status: "success", data } }),
  setDataFlow: (data) => set({ dataflow: { status: "success", data } }),
  setHistory: (data) => set({ history: { status: "success", data } }),
  setImpact: (data) => set({ impact: { status: "success", data } }),
  setTests: (data) => set({ tests: { status: "success", data } }),
  setDebug: (data) => set({ debug: { status: "success", data } }),
  setArchitecture: (data) => set({ architecture: { status: "success", data } }),

  addConversationMessage: (role, content) =>
    set((s) => ({
      conversationHistory: [...s.conversationHistory, { role, content }],
    })),
  clearConversation: () => set({ conversationHistory: [] }),
}));
