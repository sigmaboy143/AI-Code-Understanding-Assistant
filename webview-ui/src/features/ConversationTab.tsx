import React, { useState, useRef, useEffect } from "react";
import { useAppStore } from "../store/appStore";
import { CapabilityNotice } from "../components/CapabilityNotice";

// ── Shared send logic ─────────────────────────────────────────────────────────

/**
 * Produces a placeholder reply.
 *
 * The `conversations` controller exists in the backend but declares no route,
 * so there is nothing to send a question to. The reply is therefore visibly a
 * placeholder: it must never be worded so that it could be mistaken for an
 * answer derived from the user's code.
 */
async function demoSend(
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
    `No answer was generated. The backend exposes no conversation endpoint, so this is a ` +
      `placeholder reply to "${text}"${context}. It contains no analysis of your code.`
  );
  setLoading(false);
}

// ── ConversationInput — the persistent input row shown in the footer ──────────

export function ConversationInput() {
  const { codeContext, addConversationMessage, setActiveTab, useMock } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) { return; }
    // Live mode: there is no conversation endpoint, so the only reply available
    // is the placeholder below. Sending it would put a fake assistant turn in
    // the transcript under a LIVE badge, so the send is refused instead and the
    // typed text is left in the box rather than silently discarded.
    if (!useMock) { return; }
    setInput("");
    // Switch to the conversation tab so the user sees the reply
    setActiveTab("conversation");
    await demoSend(text, codeContext?.file, addConversationMessage, setLoading);
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
        placeholder={
          useMock
            ? "Ask about this code…"
            : "Unavailable: the backend exposes no conversation endpoint."
        }
        disabled={loading || !useMock}
        style={{
          flex: 1,
          padding: "5px 8px",
          background: "var(--surface2)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          color: "var(--text)",
          fontSize: "12px",
          opacity: loading || !useMock ? 0.6 : 1,
        }}
      />
      <button
        onClick={handleSend}
        disabled={loading || !input.trim() || !useMock}
        title={
          useMock
            ? "Sends to the built-in demo reply. No backend request is made."
            : "Unavailable: the backend's conversations controller declares no route."
        }
        style={{
          padding: "5px 10px",
          background: "var(--accent)",
          color: "var(--accent-fg)",
          fontSize: "14px",
          opacity: loading || !input.trim() || !useMock ? 0.5 : 1,
        }}
      >
        ↑
      </button>
    </div>
  );
}

// ── ConversationTab — full chat view with history (shown when Chat tab active) ─

export function ConversationTab() {
  const { conversationHistory, codeContext, addConversationMessage, clearConversation, useMock } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) { return; }
    // Live mode: refused rather than answered with a placeholder. See
    // ConversationInput.handleSend for the reasoning.
    if (!useMock) { return; }
    setInput("");
    await demoSend(text, codeContext?.file, addConversationMessage, setLoading);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: 8 }}>
        <CapabilityNotice
          unavailable
          message={
            useMock
              ? "The backend's conversations controller declares no route, so questions are not sent anywhere and replies are placeholders. For real analysis use the Explain tab."
              : "Conversation is not available: the backend's conversations controller declares no route, so questions are not sent anywhere. No reply is generated. Use the Explain tab for real analysis, or set aicode.useMockData to true for the demo."
          }
        />
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
          placeholder={
            useMock
              ? "Ask about this code…"
              : "Unavailable: the backend exposes no conversation endpoint."
          }
          disabled={!useMock}
          style={{
            flex: 1,
            padding: "6px 8px",
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            color: "var(--text)",
            fontSize: "12px",
            opacity: loading || !useMock ? 0.6 : 1,
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim() || !useMock}
          title={
            useMock
              ? "Sends to the built-in demo reply. No backend request is made."
              : "Unavailable: the backend's conversations controller declares no route."
          }
          style={{
            padding: "6px 10px",
            background: "var(--accent)",
            color: "var(--accent-fg)",
            fontSize: "14px",
            opacity: loading || !input.trim() || !useMock ? 0.5 : 1,
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
