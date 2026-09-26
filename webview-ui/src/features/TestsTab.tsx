import React from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { EvidenceList } from "../components/EvidenceList";
import { LoadingSpinner, ErrorState, EmptyState } from "../components/States";

export function TestsTab() {
  const { tests, codeContext } = useAppStore();

  function handleRequest() {
    if (!codeContext) { return; }
    postMessage({ type: "requestTests", payload: { context: codeContext } });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          onClick={handleRequest}
          style={{ width: "100%", padding: "6px", background: "var(--accent)", color: "var(--accent-fg)", fontSize: "12px" }}
        >
          Find Related Tests
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        {tests.status === "idle" && <EmptyState message="Find tests that cover this code." />}
        {tests.status === "loading" && <LoadingSpinner message="Finding related tests…" />}
        {tests.status === "error" && <ErrorState message={tests.error ?? "Could not find tests."} />}
        {tests.status === "success" && tests.data && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p style={{ fontSize: "13px", lineHeight: 1.6 }}>{tests.data.summary}</p>

            {tests.data.tests.map((test, i) => (
              <div
                key={i}
                style={{
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  padding: "8px 10px",
                }}
              >
                <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--success)", marginBottom: 2 }}>
                  ✓ {test.name}
                </div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: 4 }}>
                  {test.file}{test.lines ? ` : ${test.lines[0]}–${test.lines[1]}` : ""}
                </div>
                {test.description && (
                  <div style={{ fontSize: "12px" }}>{test.description}</div>
                )}
                {test.coverage !== undefined && (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: "10px", color: "var(--text-muted)", marginBottom: 2 }}>
                      Coverage: {test.coverage}%
                    </div>
                    <div style={{ height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${test.coverage}%`,
                          background: test.coverage >= 80 ? "var(--success)" : "var(--warning)",
                          borderRadius: 2,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Label text="CONFIDENCE" />
              <ConfidenceBadge level={tests.data.confidence} />
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
