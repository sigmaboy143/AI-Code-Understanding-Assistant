import React from "react";
import type { Evidence } from "../types";
import { postMessage } from "../services/vscodeApi";

interface Props {
  evidence?: Evidence[];
}

/**
 * Renders evidence items, preserving every structured field the backend sent.
 *
 * `kind` and `sourceType` are both shown because they are not the same value:
 * `kind` is the backend's taxonomy and `sourceType` is the AI Engine's own
 * `source_type`, carried through verbatim. Collapsing one into the other would
 * assert a provenance the AI Engine never stated.
 *
 * An empty list is a real, valid backend answer — "the model asserted this
 * without supporting evidence" — so it renders as an explicit statement rather
 * than being hidden or filled with placeholder items.
 */
export function EvidenceList({ evidence }: Props) {
  if (!evidence || evidence.length === 0) {
    return (
      <p style={{ color: "var(--text-muted)", fontSize: "12px", margin: 0 }}>
        No verified evidence. The backend returned an analysis with an empty evidence list.
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
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
            {/* Only a real file path becomes a navigation link. Evidence with no
                path (e.g. a bare documentation claim) is still shown, just not
                clickable, because there is nowhere to navigate to. */}
            {ev.file ? (
              <button
                onClick={() =>
                  postMessage({ type: "navigate", payload: { file: ev.file, line: ev.lines?.[0] } })
                }
                style={{
                  background: "none",
                  color: "var(--accent)",
                  padding: 0,
                  fontSize: "12px",
                  textAlign: "left",
                }}
              >
                {ev.file}
                {ev.lines ? ` : ${ev.lines[0]}–${ev.lines[1]}` : ""}
              </button>
            ) : (
              <span style={{ color: "var(--text)" }}>No file reference</span>
            )}

            {ev.kind && <Tag>{ev.kind}</Tag>}
            {ev.sourceType && ev.sourceType !== ev.kind && <Tag>{ev.sourceType}</Tag>}
            {ev.chunkId && <Tag>chunk {ev.chunkId}</Tag>}
          </div>

          {/* Commit / PR / issue exist only in mock data. The backend exposes no
              git evidence today, so these simply stay absent for real results
              rather than being invented. */}
          {ev.commit && (
            <span style={{ color: "var(--text-muted)", marginRight: 8 }}>commit: {ev.commit}</span>
          )}
          {ev.pr && (
            <span style={{ color: "var(--text-muted)", marginRight: 8 }}>PR: {ev.pr}</span>
          )}
          {ev.detail && (
            <p style={{ margin: "3px 0 0", color: "var(--text-muted)", lineHeight: 1.5 }}>{ev.detail}</p>
          )}
        </div>
      ))}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: "9px",
        padding: "0 5px",
        borderRadius: 8,
        border: "1px solid var(--border)",
        color: "var(--text-muted)",
        lineHeight: "15px",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {children}
    </span>
  );
}
