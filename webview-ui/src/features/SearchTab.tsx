import React, { useState } from "react";
import { useAppStore } from "../store/appStore";
import { postMessage } from "../services/vscodeApi";
import { EmptyState } from "../components/States";

export function SearchTab() {
  const { codeContext } = useAppStore();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<null | string[]>(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch() {
    if (!query.trim()) { return; }
    setLoading(true);
    // In mock mode: simulate results
    await new Promise((r) => setTimeout(r, 700));
    setResults([
      "src/auth/auth.service.ts — validateUser() — handles password hashing",
      "src/users/users.service.ts — createUser() — hashes password before saving",
      "src/utils/crypto.ts — hashPassword() — bcrypt implementation",
    ]);
    setLoading(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px" }}>
      <p style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: 8 }}>
        Natural-language repository search
      </p>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder='e.g. "Where is password hashing handled?"'
          style={{
            flex: 1,
            padding: "6px 8px",
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            color: "var(--text)",
            fontSize: "12px",
          }}
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          style={{
            padding: "6px 12px",
            background: "var(--accent)",
            color: "var(--accent-fg)",
            fontSize: "12px",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "…" : "Search"}
        </button>
      </div>

      {results === null && !loading && (
        <EmptyState message='Ask a question in natural language — "Where is the login handled?" or "What handles file uploads?"' />
      )}
      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: "12px", padding: 8 }}>Searching…</div>
      )}
      {results && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {results.map((r, i) => (
            <div
              key={i}
              style={{
                padding: "8px 10px",
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                fontSize: "12px",
              }}
            >
              {r}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
