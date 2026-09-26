import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";
import type { DataFlowStep } from "../types";

const STEP_COLORS: Record<DataFlowStep["type"], string> = {
  input: "var(--success)",
  function: "var(--accent)",
  service: "#9cdcfe",
  api: "#ce9178",
  database: "#dcdcaa",
  output: "#c586c0",
};

export function DataFlowTab() {
  const { dataflow, codeContext } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestDataFlow", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Trace Data Flow
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {dataflow.status === "idle" && <EmptyState message="Select code and click Trace Data Flow to visualize how data moves." />}
        {dataflow.status === "loading" && <LoadingSpinner message="Tracing data flow…" />}
        {dataflow.status === "error" && <ErrorState message={dataflow.error ?? "Could not trace data flow."} />}
        {dataflow.status === "success" && dataflow.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              {dataflow.data.steps.map((step, i) => (
                <div key={step.id}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      padding: "8px 10px",
                      background: "var(--surface2)",
                      borderRadius: "var(--radius)",
                      border: `1px solid ${STEP_COLORS[step.type] ?? "var(--border)"}`,
                    }}
                  >
                    <span
                      style={{
                        fontSize: "10px",
                        padding: "2px 6px",
                        borderRadius: 10,
                        background: STEP_COLORS[step.type] ?? "var(--border)",
                        color: "var(--bg)",
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                        marginTop: 1,
                      }}
                    >
                      {step.type.toUpperCase()}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "12px" }}>{step.label}</div>
                      {step.file && (
                        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                          {step.file}{step.line ? `:${step.line}` : ""}
                        </div>
                      )}
                      {step.description && (
                        <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: 2 }}>
                          {step.description}
                        </div>
                      )}
                    </div>
                  </div>
                  {i < dataflow.data!.steps.length - 1 && (
                    <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "16px", lineHeight: "20px" }}>↓</div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={dataflow.data.confidence} />
            </div>
            {dataflow.data.evidence && (
              <div>
                <Label text="EVIDENCE" />
                <EvidenceList evidence={dataflow.data.evidence} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Label({ text }: { text: string }) {
  return (
    <p style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
      {text}
    </p>
  );
}
