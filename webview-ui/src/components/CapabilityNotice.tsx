import React from "react";

interface Props {
  /** Set when the backend has no HTTP endpoint for this feature. */
  unavailable?: boolean;
  message?: string;
  /** True when the panel is showing demo data rather than backend results. */
  useMock?: boolean;
}

/**
 * Explains why a tab has no result, distinguishing the two cases that look
 * identical to a user staring at an empty panel.
 *
 * "The backend cannot do this yet" and "you are looking at demo data" are
 * different facts with different consequences, and conflating them would either
 * hide a genuine gap or imply a capability the backend does not have.
 */
export function CapabilityNotice({ unavailable, message, useMock }: Props) {
  if (unavailable) {
    return (
      <div
        style={{
          padding: 16,
          fontSize: "12px",
          lineHeight: 1.6,
          color: "var(--text-muted)",
          background: "var(--surface2)",
          border: "1px dashed var(--border)",
          borderRadius: "var(--radius)",
          margin: 8,
        }}
      >
        <strong style={{ color: "var(--text)", display: "block", marginBottom: 4 }}>
          Backend capability not currently available
        </strong>
        {message ?? "The backend does not expose an endpoint for this feature."}
      </div>
    );
  }

  if (useMock) {
    return (
      <div
        style={{
          padding: 10,
          fontSize: "11px",
          lineHeight: 1.6,
          color: "var(--text-muted)",
          background: "var(--surface2)",
          border: "1px dashed var(--border)",
          borderRadius: "var(--radius)",
          margin: 8,
        }}
      >
        <strong style={{ color: "var(--warning)" }}>Demo / mock mode.</strong> The content below
        is generated locally and is not a real backend or AI result. Set{" "}
        <code>aicode.useMockData</code> to <code>false</code> to use the real backend.
      </div>
    );
  }

  return null;
}
