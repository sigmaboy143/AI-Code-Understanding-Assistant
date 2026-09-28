import React from "react";

interface Props {
  message?: string;
}

export function LoadingSpinner({ message = "Analyzing…" }: Props) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        padding: 32,
        color: "var(--text-muted)",
        fontSize: "12px",
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          border: "3px solid var(--border)",
          borderTopColor: "var(--accent)",
          borderRadius: "50%",
          animation: "spin 0.7s linear infinite",
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      style={{
        padding: "16px",
        color: "var(--error)",
        fontSize: "12px",
        background: "color-mix(in srgb, var(--error) 10%, transparent)",
        borderRadius: "var(--radius)",
        margin: "8px",
      }}
    >
      <strong>⚠ Error</strong>
      <p style={{ marginTop: 4 }}>{message}</p>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div
      style={{
        padding: 24,
        textAlign: "center",
        color: "var(--text-muted)",
        fontSize: "12px",
      }}
    >
      {message}
    </div>
  );
}
