import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";

export function ArchitectureTab() {
  const { architecture } = useAppStore();

  function handleRequest() {
    postMessage({ type: "requestArchitecture", payload: {} });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Explore Architecture
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {architecture.status === "idle" && <EmptyState message="Generate an architecture overview of this repository." />}
        {architecture.status === "loading" && <LoadingSpinner message="Mapping architecture…" />}
        {architecture.status === "error" && <ErrorState message={architecture.error ?? "Could not map architecture."} />}
        {architecture.status === "success" && architecture.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{architecture.data.description}</p>

            {architecture.data.layers.map((layer, i) => (
              <div
                key={layer.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    padding: "6px 10px",
                    background: "var(--surface2)",
                    borderBottom: "1px solid var(--border)",
                    fontWeight: 600,
                    fontSize: "12px",
                  }}
                >
                  {i + 1}. {layer.label}
                </div>
                <div style={{ padding: "8px 10px" }}>
                  {layer.description && (
                    <p style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: 6 }}>
                      {layer.description}
                    </p>
                  )}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {layer.components.map((c, j) => (
                      <span
                        key={j}
                        style={{
                          padding: "2px 8px",
                          background: "var(--bg)",
                          border: "1px solid var(--border)",
                          borderRadius: 12,
                          fontSize: "11px",
                        }}
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={architecture.data.confidence} />
            </div>
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
