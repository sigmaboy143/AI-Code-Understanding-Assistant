import React, { useState, useRef, useEffect } from "react";
import { useAppStore } from "../store/appStore";

// ── Shared send logic ─────────────────────────────────────────────────────────

async function mockSend(
  text: string,
  file: string | undefined,
  addMsg: (role: "user" | "assistant", content: string) => void,
  setLoading: (v: boolean) => void
) {
  addMsg("user", text);
  setLoading(true);
  await new Promise((r) => setTimeout(r, 900));
  const context = file ? ` (in ${file})` : "";
  addMsg(
    "assistant",
    `Regarding your question about "${text}"${context}: This is where the AI-powered contextual answer will appear, informed by the repository intelligence. The answer will include evidence, confidence levels, and navigation links.`
  );
  setLoading(false);
}

// ── ConversationInput — the persistent input row shown in the footer ──────────

export function ConversationInput() {
  const { codeContext, addConversationMessage, setActiveTab } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) { return; }
    setInput("");
    // Switch to the conversation tab so the user sees the reply
    setActiveTab("conversation");
    await mockSend(text, codeContext?.file, addConversationMessage, setLoading);
  }

  return (
    <div
      style={{
        padding: "6px 8px",
        borderTop: "1px solid var(--border)",
        display: "flex",
        gap: 6,
        flexShrink: 0,
        background: "var(--surface)",
      }}
    >
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
        placeholder="Ask about this code…"
        disabled={loading}
        style={{
          flex: 1,
          padding: "5px 8px",
          background: "var(--surface2)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          color: "var(--text)",
          fontSize: "12px",
          opacity: loading ? 0.6 : 1,
        }}
      />
      <button
        onClick={handleSend}
        disabled={loading || !input.trim()}
        style={{
          padding: "5px 10px",
          background: "var(--accent)",
          color: "var(--accent-fg)",
          fontSize: "14px",
          opacity: loading || !input.trim() ? 0.5 : 1,
        }}
      >
        ↑
      </button>
    </div>
  );
}

// ── ConversationTab — full chat view with history (shown when Chat tab active) ─

export function ConversationTab() {
  const { conversationHistory, codeContext, addConversationMessage, clearConversation } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) { return; }
    setInput("");
    await mockSend(text, codeContext?.file, addConversationMessage, setLoading);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: 8 }}>
        {conversationHistory.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: "12px", textAlign: "center", marginTop: 24 }}>
            <p style={{ marginBottom: 6 }}>Ask anything about this code.</p>
            <p style={{ fontSize: "11px" }}>"What does this function do?"</p>
            <p style={{ fontSize: "11px" }}>"Why was this introduced?"</p>
            <p style={{ fontSize: "11px" }}>"What happens if I change it?"</p>
          </div>
        )}
        {conversationHistory.map((msg, i) => (
          <div
            key={i}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              padding: "7px 10px",
              borderRadius: msg.role === "user" ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
              background: msg.role === "user" ? "var(--accent)" : "var(--surface2)",
              color: msg.role === "user" ? "var(--accent-fg)" : "var(--text)",
              fontSize: "12px",
              lineHeight: 1.6,
              border: msg.role === "assistant" ? "1px solid var(--border)" : "none",
            }}
          >
            {msg.content}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-start", color: "var(--text-muted)", fontSize: "12px", padding: "4px 8px" }}>
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "8px", borderTop: "1px solid var(--border)", display: "flex", gap: 6, flexShrink: 0 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Ask about this code…"
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
          onClick={handleSend}
          disabled={loading || !input.trim()}
          style={{
            padding: "6px 10px",
            background: "var(--accent)",
            color: "var(--accent-fg)",
            fontSize: "14px",
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
        >
          ↑
        </button>
        {conversationHistory.length > 0 && (
          <button
            onClick={clearConversation}
            title="Clear conversation"
            style={{ padding: "4px 8px", background: "var(--surface2)", color: "var(--text-muted)", fontSize: "11px" }}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
