import * as vscode from "vscode";
import { getCodeContext } from "../context/contextCollector";
import { MessagingService } from "../messaging/MessagingService";
import * as api from "../api/apiService";
import { ExplanationMode, PanelTab } from "../types";

const msg = MessagingService.getInstance();

function getMode(): ExplanationMode {
  return (
    vscode.workspace
      .getConfiguration("aicode")
      .get<ExplanationMode>("explanationMode", "intermediate")
  );
}

async function runCommand(
  tab: PanelTab,
  action: () => Promise<void>
) {
  const ctx = getCodeContext();
  if (!ctx) {
    vscode.window.showWarningMessage("Open a file in the editor to use AI Code Understanding.");
    return;
  }
  msg.send({ type: "setTab", payload: { tab } });
  msg.send({ type: "loading", payload: { tab } });
  msg.send({ type: "setContext", payload: ctx });
  try {
    await action();
  } catch (err: any) {
    const message = err?.message ?? "An unexpected error occurred.";
    msg.send({ type: "error", payload: { tab, message } });
    vscode.window.showErrorMessage(`AI Code Understanding: ${message}`);
  }
}

// ── Individual command handlers ───────────────────────────────────────────────

export async function cmdExplainSelection() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  if (!ctx.selectedText) {
    vscode.window.showInformationMessage("Select some code first, then run Explain.");
    return;
  }
  await runCommand("explain", async () => {
    const result = await api.explainCode(ctx, getMode());
    msg.send({ type: "explanationResult", payload: result });
  });
}

export async function cmdExplainFile() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("explain", async () => {
    const result = await api.explainCode(ctx, getMode());
    msg.send({ type: "explanationResult", payload: result });
  });
}

export async function cmdWhyExists() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("why", async () => {
    const result = await api.explainWhy(ctx);
    msg.send({ type: "whyResult", payload: result });
  });
}

export async function cmdShowRelationships() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("relations", async () => {
    const result = await api.getRelations(ctx);
    msg.send({ type: "relationsResult", payload: result });
  });
}

export async function cmdTraceDataFlow() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("dataflow", async () => {
    const result = await api.traceDataFlow(ctx);
    msg.send({ type: "dataflowResult", payload: result });
  });
}

export async function cmdShowHistory() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("history", async () => {
    const result = await api.getHistory(ctx);
    msg.send({ type: "historyResult", payload: result });
  });
}

export async function cmdShowImpact() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("impact", async () => {
    const result = await api.analyzeImpact(ctx);
    msg.send({ type: "impactResult", payload: result });
  });
}

export async function cmdFindRelatedTests() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  await runCommand("tests", async () => {
    const result = await api.findTests(ctx);
    msg.send({ type: "testsResult", payload: result });
  });
}

export async function cmdExplainError() {
  const ctx = getCodeContext();
  if (!ctx) { return; }
  const errorText = await vscode.window.showInputBox({
    prompt: "Paste the error message (optional)",
    placeHolder: "TypeError: Cannot read properties of null...",
  });
  await runCommand("debug", async () => {
    const result = await api.debugError(ctx, errorText);
    msg.send({ type: "debugResult", payload: result });
  });
}
