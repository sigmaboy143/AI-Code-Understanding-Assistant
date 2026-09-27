import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge, ConfidenceDetail } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { CapabilityNotice } from "../components/CapabilityNotice";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";
import type { ExplanationMode, ExplanationResponse, UiSymbol } from "../types";

const MODES: ExplanationMode[] = ["beginner", "intermediate", "advanced"];

export function ExplainTab() {
  const { explanation, codeContext, explanationMode, useMock, setExplanationMode } = useAppStore();

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
        {explanation.unavailable && (
          <CapabilityNotice unavailable message={explanation.unavailableMessage} />
        )}

        {explanation.status === "idle" && !explanation.unavailable && (
          <EmptyState message='Select code in the editor, then click a mode above or use the context menu → "Explain Selected Code".' />
        )}
        {explanation.status === "loading" && (
          <LoadingSpinner message="Understanding this code…" />
        )}
        {explanation.status === "error" && (
          <ErrorState message={explanation.error ?? "Unable to analyze this code."} />
        )}
        {explanation.status === "success" && explanation.data && (
          <ExplanationResult data={explanation.data} useMock={useMock} />
        )}
      </div>
    </div>
  );
}

function ExplanationResult({ data, useMock }: { data: ExplanationResponse; useMock: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <CapabilityNotice useMock={useMock && data.source !== "backend"} />

      <Section title="WHAT" body={data.what} />
      {/* A real backend response carries one summary, not separate how/why
          findings. The sections stay in place, and state plainly that the
          backend did not provide them, rather than being filled with text the
          AI Engine never produced. */}
      <Section title="HOW" body={data.how} emptyHint="The backend did not return a detailed breakdown for this analysis." />
      <Section title="WHY" body={data.why} emptyHint="The backend does not provide a rationale separately from the summary." />
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

      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <SectionTitle title="CONFIDENCE" />
          <ConfidenceBadge level={data.confidence} />
        </div>
        <ConfidenceDetail meta={data.confidenceMeta} />
      </div>

      {data.symbols && data.symbols.length > 0 && (
        <div>
          <SectionTitle title="SYMBOLS" />
          <SymbolList symbols={data.symbols} />
        </div>
      )}

      <div>
        <SectionTitle title="EVIDENCE" />
        <EvidenceList evidence={data.evidence} />
      </div>

      {(data.requestId || data.analysedAt || data.generatedAt) && (
        <div style={{ fontSize: "10px", color: "var(--text-muted)", lineHeight: 1.6 }}>
          {data.requestId && <div>request: {data.requestId}</div>}
          {(data.analysedAt || data.generatedAt) && <div>analysed: {data.analysedAt ?? data.generatedAt}</div>}
        </div>
      )}
    </div>
  );
}

function SymbolList({ symbols }: { symbols: UiSymbol[] }) {
  return (
    <ul style={{ paddingLeft: 16, fontSize: "12px", color: "var(--text-muted)" }}>
      {symbols.map((s) => (
        <li key={s.id} style={{ marginBottom: 3 }}>
          <span style={{ color: "var(--text)" }}>{s.name}</span>
          <span> ({s.kind})</span>
          {s.filePath && s.startLine !== undefined && (
            <span>
              {" "}— {s.filePath}:{s.startLine}
              {s.endLine !== undefined && s.endLine !== s.startLine ? `-${s.endLine}` : ""}
            </span>
          )}
          {s.signature && <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{s.signature}</div>}
        </li>
      ))}
    </ul>
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

function Section({ title, body, emptyHint }: { title: string; body: string; emptyHint?: string }) {
  return (
    <div>
      <SectionTitle title={title} />
      {body ? (
        <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{body}</p>
      ) : (
        <p style={{ fontSize: "12px", lineHeight: 1.6, color: "var(--text-muted)", fontStyle: "italic" }}>
          {emptyHint ?? "Not provided."}
        </p>
      )}
    </div>
  );
}
