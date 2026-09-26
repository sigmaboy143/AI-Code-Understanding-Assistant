import React, { useState } from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";

const CONFIDENCE_COLORS = {
  confirmed: "var(--success)",
  inferred: "var(--warning)",
  unknown: "var(--text-muted)",
};

export function DebugTab() {
  const { debug, codeContext } = useAppStore();
  const [errorText, setErrorText] = useState("");

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestDebug", payload: { context: codeContext, error: errorText || undefined } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <input
          value={errorText}
          onChange={(e) => setErrorText(e.target.value)}
          placeholder="Paste error message (optional)…"
          style={{
            width: "100%",
            padding: "5px 8px",
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            color: "var(--text)",
            fontSize: "12px",
            marginBottom: 6,
            fontFamily: "var(--font-mono)",
          }}
        />
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Analyze & Debug
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {debug.status === "idle" && <EmptyState message="Paste an error and click Analyze to diagnose the root cause." />}
        {debug.status === "loading" && <LoadingSpinner message="Diagnosing error…" />}
        {debug.status === "error" && <ErrorState message={debug.error ?? "Could not analyze error."} />}
        {debug.status === "success" && debug.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ padding: "8px 10px", background: "color-mix(in srgb, var(--error) 15%, transparent)", borderRadius: "var(--radius)", borderLeft: "3px solid var(--error)" }}>
              <Label text="ERROR" />
              <code style={{ fontSize: "11px", color: "var(--error)", wordBreak: "break-all" }}>
                {debug.data.error}
              </code>
            </div>

            <div>
              <Label text="ROOT CAUSE" />
              <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{debug.data.rootCause}</p>
            </div>

            <div>
              <Label text="CALL CHAIN" />
              {debug.data.callChain.map((step, i) => (
                <div key={i} style={{ fontSize: "12px", padding: "2px 0", fontFamily: "var(--font-mono)", color: i === debug.data!.callChain.length - 1 ? "var(--error)" : "var(--text)" }}>
                  {i > 0 && <span style={{ color: "var(--text-muted)", marginRight: 4 }}>↓</span>}
                  {step}
                </div>
              ))}
            </div>

            <div>
              <Label text="POSSIBLE CAUSES" />
              {debug.data.possibleCauses.map((c, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    padding: "5px 0",
                    borderBottom: "1px solid var(--border)",
                    fontSize: "12px",
                  }}
                >
                  <ConfidenceBadge level={c.confidence} />
                  <span>{c.cause}</span>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={debug.data.confidence} />
            </div>

            {debug.data.evidence && (
              <div>
                <Label text="EVIDENCE" />
                <EvidenceList evidence={debug.data.evidence} />
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
