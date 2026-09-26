import React from "react";
import type { Evidence } from "../types";
import { postMessage } from "../services/vscodeApi";

interface Props {
  evidence: Evidence[];
}

export function EvidenceList({ evidence }: Props) {
  if (!evidence?.length) {
    return (
      <p style={{ color: "var(--text-muted)", fontSize: "12px" }}>
        No verified evidence found.
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {evidence.map((ev, i) => (
        <div
          key={i}
          style={{
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "6px 10px",
            fontSize: "12px",
          }}
        >
          <button
            onClick={() =>
              postMessage({ type: "navigate", payload: { file: ev.file, line: ev.lines?.[0] } })
            }
            style={{
              background: "none",
              color: "var(--accent)",
              padding: 0,
              fontSize: "12px",
              display: "block",
              textAlign: "left",
              marginBottom: 2,
            }}
          >
            {ev.file}
            {ev.lines ? ` : ${ev.lines[0]}–${ev.lines[1]}` : ""}
          </button>
          {ev.commit && (
            <span style={{ color: "var(--text-muted)", marginRight: 8 }}>
              commit: {ev.commit}
            </span>
          )}
          {ev.pr && (
            <span style={{ color: "var(--text-muted)", marginRight: 8 }}>
              PR: {ev.pr}
            </span>
          )}
          {ev.description && (
            <span style={{ color: "var(--text-muted)" }}>{ev.description}</span>
          )}
        </div>
      ))}
    </div>
  );
}
