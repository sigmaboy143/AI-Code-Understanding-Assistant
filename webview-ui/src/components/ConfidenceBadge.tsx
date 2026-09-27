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
  /**
   * The three-state level. Treated as untrusted input: a missing, empty or
   * unrecognised value renders as "Unknown" rather than throwing or rendering
   * an undefined colour. The backend's own vocabulary is wider than these three
   * states, so this component must never be handed a raw backend level.
   */
  level?: ConfidenceLevel | null;
}

/**
 * Renders confidence, optionally annotated with what the backend actually said.
 *
 * `rawLevel` and `reasoning` exist so the adapter's translation is auditable.
 * When the backend said "low" and the badge shows "Unknown", the raw word is
 * still on screen — the UI never quietly overstates or restates confidence.
 */
export function ConfidenceBadge({ level }: Props) {
  const safeLevel: ConfidenceLevel =
    level === "confirmed" || level === "inferred" || level === "unknown"
      ? level
      : "unknown";

  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 7px",
        borderRadius: "10px",
        fontSize: "11px",
        fontWeight: 600,
        border: `1px solid ${COLORS[safeLevel]}`,
        color: COLORS[safeLevel],
        lineHeight: "18px",
      }}
    >
      {LABELS[safeLevel]}
    </span>
  );
}

/**
 * Shows the backend's confidence metadata verbatim beneath the badge.
 *
 * Renders nothing at all when the backend supplied no metadata, so a response
 * without confidence does not grow an empty section.
 */
export function ConfidenceDetail({
  meta,
}: {
  meta?: { level?: string; score?: number; model?: string; reasoning?: string };
}) {
  if (!meta) {
    return null;
  }

  const parts: string[] = [];
  if (meta.level) {
    parts.push(`level: ${meta.level}`);
  }
  // Absence of a score means "not provided" and must never render as 0.
  if (typeof meta.score === "number" && Number.isFinite(meta.score)) {
    parts.push(`score: ${Math.round(meta.score * 100)}%`);
  }
  if (meta.model) {
    parts.push(`model: ${meta.model}`);
  }

  if (parts.length === 0 && !meta.reasoning) {
    return null;
  }

  return (
    <div style={{ fontSize: "11px", color: "var(--text-muted)", lineHeight: 1.6 }}>
      {parts.length > 0 && <div>{parts.join(" · ")}</div>}
      {meta.reasoning && <div style={{ marginTop: 2 }}>{meta.reasoning}</div>}
    </div>
  );
}
