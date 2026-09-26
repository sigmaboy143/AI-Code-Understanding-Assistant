import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";
import type { RelationNode, RelationEdge } from "../types";

export function RelationsTab() {
  const { relations, codeContext } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestRelations", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Show Relationships
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {relations.status === "idle" && <EmptyState message="Select code and click Show Relationships to explore connections." />}
        {relations.status === "loading" && <LoadingSpinner message="Mapping relationships…" />}
        {relations.status === "error" && <ErrorState message={relations.error ?? "Could not map relationships."} />}
        {relations.status === "success" && relations.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <RelationGraph nodes={relations.data.nodes} edges={relations.data.edges} />
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={relations.data.confidence} />
            </div>
            {relations.data.evidence && (
              <div>
                <Label text="EVIDENCE" />
                <EvidenceList evidence={relations.data.evidence} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const TYPE_COLORS: Record<RelationNode["type"], string> = {
  file: "var(--accent)",
  function: "var(--success)",
  class: "#c586c0",
  api: "#ce9178",
  database: "#dcdcaa",
  service: "#9cdcfe",
};

function RelationGraph({ nodes, edges }: { nodes: RelationNode[]; edges: RelationEdge[] }) {
  return (
    <div>
      <Label text="NODES" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        {nodes.map((n) => (
          <span
            key={n.id}
            style={{
              padding: "2px 8px",
              border: `1px solid ${TYPE_COLORS[n.type] ?? "var(--border)"}`,
              borderRadius: 12,
              fontSize: "11px",
              color: TYPE_COLORS[n.type] ?? "var(--text)",
            }}
          >
            {n.label}
          </span>
        ))}
      </div>
      <Label text="CONNECTIONS" />
      {edges.map((e, i) => {
        const from = nodes.find((n) => n.id === e.from)?.label ?? e.from;
        const to = nodes.find((n) => n.id === e.to)?.label ?? e.to;
        return (
          <div key={i} style={{ fontSize: "12px", padding: "3px 0", color: "var(--text-muted)" }}>
            <span style={{ color: "var(--text)" }}>{from}</span>
            <span style={{ margin: "0 6px" }}>
              {e.label ? `→ ${e.label} →` : "→"}
            </span>
            <span style={{ color: "var(--text)" }}>{to}</span>
          </div>
        );
      })}
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
