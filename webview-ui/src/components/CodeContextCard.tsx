import React from "react";
import type { CodeContext } from "../types";

interface Props {
  context: CodeContext | null;
}

export function CodeContextCard({ context }: Props) {
  if (!context) {
    return (
      <div
        style={{
          padding: "8px 12px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          color: "var(--text-muted)",
          fontSize: "12px",
        }}
      >
        No file open
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "8px 12px",
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        fontSize: "12px",
      }}
    >
      <div
        style={{
          color: "var(--text-muted)",
          marginBottom: 2,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={context.file}
      >
        📄 {context.file}
      </div>
      {context.selectedText && (
        <div
          style={{
            color: "var(--accent)",
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={context.selectedText}
        >
          Lines {context.startLine}–{context.endLine}:{" "}
          <em>{context.selectedText.trim().split("\n")[0].slice(0, 60)}</em>
        </div>
      )}
    </div>
  );
}
