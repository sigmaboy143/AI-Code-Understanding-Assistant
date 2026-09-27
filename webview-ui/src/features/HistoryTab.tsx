import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { TabGate } from "../components/TabGate";

export function HistoryTab() {
  const { history, codeContext, useMock } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestHistory", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Show History
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        <TabGate
          status={history.status}
          error={history.error}
          unavailable={history.unavailable}
          unavailableMessage={history.unavailableMessage}
          useMock={useMock}
          loadingMessage="Loading git history…"
          errorFallback="Could not load history."
          idleMessage="Show the git history and evolution of this code."
        />
        {history.status === "success" && history.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{history.data.summary}</p>

            <Label text="TIMELINE" />
            <div style={{ position: "relative", paddingLeft: 16 }}>
              <div style={{
                position: "absolute",
                left: 6,
                top: 0,
                bottom: 0,
                width: 2,
                background: "var(--border)",
              }} />
              {history.data.commits.map((c, i) => (
                <div key={i} style={{ position: "relative", marginBottom: 14 }}>
                  <div style={{
                    position: "absolute",
                    left: -14,
                    top: 4,
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "var(--accent)",
                  }} />
                  <div style={{ fontSize: "12px" }}>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", marginRight: 6 }}>
                      {c.hash.slice(0, 7)}
                    </span>
                    <span style={{ fontWeight: 500 }}>{c.message}</span>
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: 1 }}>
                    {c.author} · {c.date}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={history.data.confidence} />
            </div>
            {history.data.evidence && (
              <div>
                <Label text="EVIDENCE" />
                <EvidenceList evidence={history.data.evidence} />
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
