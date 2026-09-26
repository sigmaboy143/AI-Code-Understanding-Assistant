import React from "react";
import type { ConfidenceLevel } from "../types";

const LABELS: Record<ConfidenceLevel, string> = {
  confirmed: "Confirmed",
  inferred: "Inferred",
  unknown: "Unknown",
};

const COLORS: Record<ConfidenceLevel, string> = {
  confirmed: "var(--success)",
  inferred: "var(--warning)",
  unknown: "var(--text-muted)",
};

interface Props {
  level: ConfidenceLevel;
}

export function ConfidenceBadge({ level }: Props) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 7px",
        borderRadius: "10px",
        fontSize: "11px",
        fontWeight: 600,
        border: `1px solid ${COLORS[level]}`,
        color: COLORS[level],
        lineHeight: "18px",
      }}
    >
      {LABELS[level]}
    </span>
  );
}
