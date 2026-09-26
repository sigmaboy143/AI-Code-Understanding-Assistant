import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";
import type { ExplanationMode, ExplanationResponse } from "../types";

const MODES: ExplanationMode[] = ["beginner", "intermediate", "advanced"];

export function ExplainTab() {
  const { explanation, codeContext, explanationMode, setExplanationMode } = useAppStore();

  function handleRequest(mode: ExplanationMode) {
    if (!codeContext) { return; }
    setExplanationMode(mode);
    postMessage({
      type: "requestExplain",
      payload: { context: codeContext, mode },
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Mode selector */}
      <div
        style={{
          display: "flex",
          gap: 4,
          padding: "8px 12px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => handleRequest(m)}
            style={{
              flex: 1,
              padding: "4px 6px",
              background: explanationMode === m ? "var(--accent)" : "var(--surface2)",
              color: explanationMode === m ? "var(--accent-fg)" : "var(--text)",
              textTransform: "capitalize",
              fontSize: "11px",
            }}
          >
            {m}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {explanation.status === "idle" && (
          <EmptyState message='Select code in the editor, then click a mode above or use the context menu → "Explain Selected Code".' />
        )}
        {explanation.status === "loading" && (
          <LoadingSpinner message="Understanding this code…" />
        )}
        {explanation.status === "error" && (
          <ErrorState message={explanation.error ?? "Unable to analyze this code."} />
        )}
        {explanation.status === "success" && explanation.data && (
          <ExplanationResult data={explanation.data} />
        )}
      </div>
    </div>
  );
}

function ExplanationResult({ data }: { data: ExplanationResponse }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Section title="WHAT" body={data.what} />
      <Section title="HOW" body={data.how} />
      <Section title="WHY" body={data.why} />
      {data.where && <Section title="WHERE" body={data.where} />}

      {data.related && data.related.length > 0 && (
        <div>
          <SectionTitle title="RELATED" />
          <ul style={{ paddingLeft: 16, fontSize: "12px", color: "var(--text-muted)" }}>
            {data.related.map((r, i) => <li key={i} style={{ marginBottom: 2 }}>{r}</li>)}
          </ul>
        </div>
      )}

      {data.tests && data.tests.length > 0 && (
        <div>
          <SectionTitle title="TESTS" />
          <ul style={{ paddingLeft: 16, fontSize: "12px", color: "var(--text-muted)" }}>
            {data.tests.map((t, i) => <li key={i} style={{ marginBottom: 2 }}>{t}</li>)}
          </ul>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <SectionTitle title="CONFIDENCE" />
        <ConfidenceBadge level={data.confidence} />
      </div>

      {data.evidence && data.evidence.length > 0 && (
        <div>
          <SectionTitle title="EVIDENCE" />
          <EvidenceList evidence={data.evidence} />
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <p
      style={{
        fontSize: "10px",
        fontWeight: 700,
        letterSpacing: "0.08em",
        color: "var(--text-muted)",
        marginBottom: 4,
        textTransform: "uppercase",
      }}
    >
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
