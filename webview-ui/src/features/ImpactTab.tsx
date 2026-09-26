import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";
import type { ImpactNode } from "../types";

const TYPE_COLORS: Record<ImpactNode["type"], string> = {
  direct: "var(--error)",
  indirect: "var(--warning)",
  test: "var(--success)",
  api: "#9cdcfe",
};

export function ImpactTab() {
  const { impact, codeContext } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestImpact", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Analyze Impact
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {impact.status === "idle" && <EmptyState message="Discover what would be affected if this code changed." />}
        {impact.status === "loading" && <LoadingSpinner message="Analyzing impact…" />}
        {impact.status === "error" && <ErrorState message={impact.error ?? "Could not analyze impact."} />}
        {impact.status === "success" && impact.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div
              style={{
                padding: "8px 12px",
                background: "var(--surface2)",
                borderRadius: "var(--radius)",
                borderLeft: "3px solid var(--accent)",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              {impact.data.root}
            </div>

            <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{impact.data.summary}</p>

            <Label text="AFFECTED COMPONENTS" />
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {impact.data.nodes.map((node) => (
                <div
                  key={node.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "5px 8px",
                    background: "var(--surface2)",
                    borderRadius: "var(--radius)",
                    fontSize: "12px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      padding: "1px 6px",
                      borderRadius: 10,
                      background: TYPE_COLORS[node.type],
                      color: "var(--bg)",
                      fontWeight: 700,
                    }}
                  >
                    {node.type.toUpperCase()}
                  </span>
                  <span>{node.label}</span>
                  {node.file && (
                    <span style={{ color: "var(--text-muted)", fontSize: "11px", marginLeft: "auto" }}>
                      {node.file}
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={impact.data.confidence} />
            </div>
            {impact.data.evidence && (
              <div>
                <Label text="EVIDENCE" />
                <EvidenceList evidence={impact.data.evidence} />
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
