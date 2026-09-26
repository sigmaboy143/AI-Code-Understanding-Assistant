import React from "react";
import { useExtensionBridge } from "./hooks/useExtensionBridge";
import { useAppStore } from "./store/appStore";
import { CodeContextCard } from "./components/CodeContextCard";
import { ExplainTab } from "./features/ExplainTab";
import { WhyTab } from "./features/WhyTab";
import { RelationsTab } from "./features/RelationsTab";
import { DataFlowTab } from "./features/DataFlowTab";
import { HistoryTab } from "./features/HistoryTab";
import { ImpactTab } from "./features/ImpactTab";
import { TestsTab } from "./features/TestsTab";
import { DebugTab } from "./features/DebugTab";
import { ArchitectureTab } from "./features/ArchitectureTab";
import { SearchTab } from "./features/SearchTab";
import { ConversationTab } from "./features/ConversationTab";
import type { PanelTab } from "./types";

const TABS: Array<{ id: PanelTab; label: string; title: string }> = [
  { id: "explain", label: "Explain", title: "Explain code" },
  { id: "why", label: "Why", title: "Why does this exist?" },
  { id: "relations", label: "Relations", title: "Show relationships" },
  { id: "dataflow", label: "Data", title: "Trace data flow" },
  { id: "history", label: "History", title: "Git history" },
  { id: "impact", label: "Impact", title: "Analyze impact" },
  { id: "tests", label: "Tests", title: "Related tests" },
  { id: "debug", label: "Debug", title: "Debug / diagnose errors" },
  { id: "architecture", label: "Arch", title: "Architecture overview" },
  { id: "search", label: "Search", title: "Natural language search" },
];

export default function App() {
  useExtensionBridge();
  const { codeContext, activeTab, setActiveTab, useMock } = useAppStore();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "8px 12px 4px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontWeight: 700, fontSize: "12px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--accent)" }}>
            AI Code Understanding
          </span>
          {useMock && (
            <span
              title="Using mock data — configure aicode.useMockData to switch to real backend"
              style={{
                fontSize: "9px",
                padding: "1px 5px",
                borderRadius: 8,
                border: "1px solid var(--warning)",
                color: "var(--warning)",
              }}
            >
              MOCK
            </span>
          )}
        </div>
      </div>

      {/* Context card */}
      <CodeContextCard context={codeContext} />

      {/* Tab strip — first row */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
          background: "var(--surface)",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            title={tab.title}
            style={{
              padding: "5px 8px",
              background: "none",
              color: activeTab === tab.id ? "var(--accent)" : "var(--text-muted)",
              borderBottom: activeTab === tab.id ? "2px solid var(--accent)" : "2px solid transparent",
              fontSize: "11px",
              borderRadius: 0,
              fontWeight: activeTab === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
        {/* Ask tab always visible */}
        <button
          onClick={() => setActiveTab("search" as PanelTab)}
          title="Natural language search"
          style={{
            marginLeft: "auto",
            padding: "5px 8px",
            background: "none",
            color: "var(--text-muted)",
            fontSize: "11px",
            borderRadius: 0,
          }}
        >
          🔍
        </button>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {activeTab === "explain" && <ExplainTab />}
        {activeTab === "why" && <WhyTab />}
        {activeTab === "relations" && <RelationsTab />}
        {activeTab === "dataflow" && <DataFlowTab />}
        {activeTab === "history" && <HistoryTab />}
        {activeTab === "impact" && <ImpactTab />}
        {activeTab === "tests" && <TestsTab />}
        {activeTab === "debug" && <DebugTab />}
        {activeTab === "architecture" && <ArchitectureTab />}
        {activeTab === "search" && <SearchTab />}
        {activeTab === "onboarding" && <ConversationTab />}
      </div>

      {/* Persistent conversation / ask-about-code footer (always visible) */}
      <div style={{ borderTop: "2px solid var(--border)", flexShrink: 0, maxHeight: 220, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <ConversationTab />
      </div>
    </div>
  );
}
