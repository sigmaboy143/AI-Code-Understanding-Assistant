import React, { useState } from "react";
import { CapabilityNotice } from "../components/CapabilityNotice";
import { EmptyState } from "../components/States";
import { useAppStore } from "../store/appStore";

/**
 * Natural-language repository search.
 *
 * The backend has no search route — the closest declarations, `documentation`
 * and `conversations`, are controllers with no route handler at all. So this
 * tab has no real mode: it is a demo of the intended interaction, and it says
 * so rather than returning invented result strings that read like real
 * repository matches.
 *
 * In live mode the demo is switched off rather than relabelled. The three hard
 * coded strings below are indistinguishable from real matches once they are on
 * screen, so showing them against a LIVE badge would be presenting invented
 * repository content as something the AI Engine found. The tab therefore
 * refuses to search and shows the capability notice instead.
 */
export function SearchTab() {
  const { useMock } = useAppStore();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<null | string[]>(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch() {
    if (!query.trim()) { return; }
    // No backend route exists to call, so in live mode there is nothing to
    // search with and nothing honest to return.
    if (!useMock) { return; }
    setLoading(true);
    // No backend call is made: there is nothing to call. The delay only
    // preserves the interaction shape for UI review.
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
          disabled={loading || !useMock}
          title={
            useMock
              ? "Runs the built-in demo search. No backend request is made."
              : "Unavailable: the backend exposes no search endpoint."
          }
          style={{
            padding: "6px 12px",
            background: "var(--accent)",
            color: "var(--accent-fg)",
            fontSize: "12px",
            opacity: loading || !useMock ? 0.6 : 1,
          }}
        >
          {loading ? "…" : "Search"}
        </button>
      </div>

      <CapabilityNotice
        unavailable
        message={
          useMock
            ? "The backend does not expose a search endpoint. This tab demonstrates the intended interaction and its results are fixed demo strings, not real repository matches."
            : "Search is not available: the backend does not expose a search endpoint, so there is nothing to query. No results are shown rather than inventing repository matches. Set aicode.useMockData to true to explore the demo interaction."
        }
      />

      {results === null && !loading && (
        <EmptyState message='Ask a question in natural language — "Where is the login handled?" or "What handles file uploads?"' />
      )}
      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: "12px", padding: 8 }}>Searching…</div>
      )}
      {results && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <p style={{ fontSize: "10px", color: "var(--text-muted)", margin: 0 }}>
            Demo results — these strings are hard-coded, not returned by any service.
          </p>
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
