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

interface TabState<T> {
  status: LoadingState;
  data?: T;
  error?: string;
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

function tabLoading(tab: PanelTab, state: AppState): Partial<AppState> {
  return { [tab]: { status: "loading" } } as Partial<AppState>;
}

function tabError(tab: PanelTab, message: string): Partial<AppState> {
  return { [tab]: { status: "error", error: message } } as Partial<AppState>;
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

  setLoading: (tab) => set((s) => ({ ...s, [tab]: { status: "loading" } })),
  setError: (tab, message) =>
    set((s) => ({ ...s, [tab]: { status: "error", error: message } })),

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
