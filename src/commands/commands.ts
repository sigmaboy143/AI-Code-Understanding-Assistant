import * as vscode from "vscode";
import {
  assertCodeWithinBackendLimit,
  getCodeContext,
  resolveAnalysisCode,
} from "../context/contextCollector";
import { MessagingService } from "../messaging/MessagingService";
import * as api from "../api/apiService";
import { isBackendCapabilityError } from "../api/analysisAdapter";
import { BackendCapability, ExplanationMode, PanelTab } from "../types";

const msg = MessagingService.getInstance();

function getMode(): ExplanationMode {
  return (
    vscode.workspace
      .getConfiguration("aicode")
      .get<ExplanationMode>("explanationMode", "intermediate")
  );
}

/**
 * Runs a feature request and routes the outcome to the webview.
 *
 * Two failure modes are deliberately distinguished. A capability error means
 * the backend has no such feature, and is reported as a notice. Anything else
 * is a real failure and is reported as an error. Collapsing the two would make
 * a missing backend feature look like an outage.
 */
async function runCommand(tab: PanelTab, action: () => Promise<void>) {
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
  } catch (err: unknown) {
    if (isBackendCapabilityError(err)) {
      msg.send({
        type: "capability",
        payload: {
          tab,
          capability: err.capability as BackendCapability,
          message: err.message,
        },
      });
      return;
    }
    const message = err instanceof Error ? err.message : "An unexpected error occurred.";
    msg.send({ type: "error", payload: { tab, message } });
    vscode.window.showErrorMessage(`AI Code Understanding: ${message}`);
  }
}

/**
 * Shared body for the two explain commands: resolve text, guard, analyse.
 *
 * Text resolution happens inside `runCommand`'s error boundary. A command
 * handler's rejected promise is otherwise swallowed by VS Code, leaving the user
 * with no feedback and the panel stuck on its loading state.
 */
async function runAnalysis(
  tab: PanelTab,
  requireFullDocument: boolean
): Promise<void> {
  const ctx = getCodeContext();
  if (!ctx) {
    vscode.window.showWarningMessage("Open a file in the editor to use AI Code Understanding.");
    return;
  }

  await runCommand(tab, async () => {
    const code = resolveAnalysisCode(ctx, requireFullDocument);
    assertCodeWithinBackendLimit(code);
    const mode = getMode();
    const result = requireFullDocument
      ? await api.explainFile(ctx, code, mode)
      : await api.explainCode(ctx, code, mode);
    msg.send({ type: "explanationResult", payload: result });
  });
}

// ── Individual command handlers ───────────────────────────────────────────────

/** "Explain Selected Code" — analyses the selection via POST /analysis/code. */
export async function cmdExplainSelection() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  if (!ctx.selectedText) {
    vscode.window.showInformationMessage("Select some code first, then run Explain.");
    return;
  }
  await runAnalysis("explain", false);
}

/** "Explain File" — analyses the complete document via POST /analysis/file. */
export async function cmdExplainFile() {
  await runAnalysis("explain", true);
}

export async function cmdWhyExists() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("why", async () => {
    const result = await api.explainWhy(ctx);
    msg.send({ type: "whyResult", payload: result });
  });
}

export async function cmdShowRelationships() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("relations", async () => {
    const result = await api.getRelations(ctx);
    msg.send({ type: "relationsResult", payload: result });
  });
}

export async function cmdTraceDataFlow() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("dataflow", async () => {
    const result = await api.traceDataFlow(ctx);
    msg.send({ type: "dataflowResult", payload: result });
  });
}

export async function cmdShowHistory() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("history", async () => {
    const result = await api.getHistory(ctx);
    msg.send({ type: "historyResult", payload: result });
  });
}

export async function cmdShowImpact() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("impact", async () => {
    const result = await api.analyzeImpact(ctx);
    msg.send({ type: "impactResult", payload: result });
  });
}

export async function cmdFindRelatedTests() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  await runCommand("tests", async () => {
    const result = await api.findTests(ctx);
    msg.send({ type: "testsResult", payload: result });
  });
}

export async function cmdExplainError() {
  const ctx = getCodeContext();
  if (!ctx) {
    return;
  }
  const errorText = await vscode.window.showInputBox({
    prompt: "Paste the error message (optional)",
    placeHolder: "TypeError: Cannot read properties of null...",
  });
  await runCommand("debug", async () => {
    const result = await api.debugError(ctx, errorText);
    msg.send({ type: "debugResult", payload: result });
  });
}
