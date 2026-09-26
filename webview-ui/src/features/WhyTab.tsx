import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";

export function WhyTab() {
  const { why, codeContext } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestWhy", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{
            width: "100%",
            padding: "6px",
            background: "var(--accent)",
            color: "var(--accent-fg)",
            fontSize: "12px",
          }}
        >
          Why Does This Exist?
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {why.status === "idle" && (
          <EmptyState message='Click "Why Does This Exist?" to understand the purpose and history of this code.' />
        )}
        {why.status === "loading" && <LoadingSpinner message="Investigating origin and purpose…" />}
        {why.status === "error" && <ErrorState message={why.error ?? "Unable to determine why."} />}
        {why.status === "success" && why.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Section title="REASON" body={why.data.reason} />
            <Section title="CONTEXT" body={why.data.context} />

            {why.data.commits && why.data.commits.length > 0 && (
              <div>
                <SectionTitle title="COMMITS" />
                {why.data.commits.map((c, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: "12px",
                      padding: "6px 8px",
                      background: "var(--surface2)",
                      borderRadius: "var(--radius)",
                      marginBottom: 4,
                    }}
                  >
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", marginRight: 8 }}>
                      {c.hash.slice(0, 7)}
                    </span>
                    <span>{c.message}</span>
                    <span style={{ color: "var(--text-muted)", float: "right", fontSize: "11px" }}>
                      {c.author} · {c.date}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {why.data.issues && why.data.issues.length > 0 && (
              <div>
                <SectionTitle title="RELATED ISSUES" />
                <ul style={{ paddingLeft: 16, fontSize: "12px", color: "var(--text-muted)" }}>
                  {why.data.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                </ul>
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <SectionTitle title="CONFIDENCE" />
              <ConfidenceBadge level={why.data.confidence} />
            </div>

            {why.data.evidence && (
              <div>
                <SectionTitle title="EVIDENCE" />
                <EvidenceList evidence={why.data.evidence} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <p style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
      {title}
    </p>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <SectionTitle title={title} />
      <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{body}</p>
    </div>
  );
}
