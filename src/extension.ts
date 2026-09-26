import * as vscode from "vscode";
import { AiCodePanel, AiCodeSidePanelProvider } from "./panels/AiCodePanel";
import { MessagingService } from "./messaging/MessagingService";
import {
  cmdExplainSelection,
  cmdExplainFile,
  cmdWhyExists,
  cmdShowRelationships,
  cmdTraceDataFlow,
  cmdShowHistory,
  cmdShowImpact,
  cmdFindRelatedTests,
  cmdExplainError,
} from "./commands/commands";
import * as api from "./api/apiService";
import { getCodeContext } from "./context/contextCollector";
import { WebviewToExtensionMessage, PanelTab } from "./types";

export function activate(context: vscode.ExtensionContext) {
  console.log("AI Code Understanding Assistant activated");

  const messaging = MessagingService.getInstance();

  // ── Helper: wraps an API call with loading/error state for the webview ──
  async function runApiCall<T>(
    tab: PanelTab,
    fn: () => Promise<T>,
    onSuccess: (result: T) => void
  ) {
    messaging.send({ type: "loading", payload: { tab } });
    try {
      const result = await fn();
      onSuccess(result);
    } catch (err: any) {
      const message: string = err?.message ?? "An unexpected error occurred.";
      messaging.send({ type: "error", payload: { tab, message } });
    }
  }

  // ── Webview message handler ──────────────────────────────────────────────
  async function handleWebviewMessage(msg: WebviewToExtensionMessage) {
    // Infrastructure: ready + navigate
    await messaging.handle(msg);

    // Feature requests initiated from inside the webview
    switch (msg.type) {
      case "requestExplain":
        await runApiCall("explain", () => api.explainCode(msg.payload.context, msg.payload.mode), (r) =>
          messaging.send({ type: "explanationResult", payload: r })
        );
        break;

      case "requestWhy":
        await runApiCall("why", () => api.explainWhy(msg.payload.context), (r) =>
          messaging.send({ type: "whyResult", payload: r })
        );
        break;

      case "requestRelations":
        await runApiCall("relations", () => api.getRelations(msg.payload.context), (r) =>
          messaging.send({ type: "relationsResult", payload: r })
        );
        break;

      case "requestDataFlow":
        await runApiCall("dataflow", () => api.traceDataFlow(msg.payload.context), (r) =>
          messaging.send({ type: "dataflowResult", payload: r })
        );
        break;

      case "requestHistory":
        await runApiCall("history", () => api.getHistory(msg.payload.context), (r) =>
          messaging.send({ type: "historyResult", payload: r })
        );
        break;

      case "requestImpact":
        await runApiCall("impact", () => api.analyzeImpact(msg.payload.context), (r) =>
          messaging.send({ type: "impactResult", payload: r })
        );
        break;

      case "requestTests":
        await runApiCall("tests", () => api.findTests(msg.payload.context), (r) =>
          messaging.send({ type: "testsResult", payload: r })
        );
        break;

      case "requestDebug":
        await runApiCall("debug", () => api.debugError(msg.payload.context, msg.payload.error), (r) =>
          messaging.send({ type: "debugResult", payload: r })
        );
        break;

      case "requestArchitecture":
        await runApiCall("architecture", () => api.getArchitecture(msg.payload.repositoryId), (r) =>
          messaging.send({ type: "architectureResult", payload: r })
        );
        break;
    }
  }

  // ── Register the activity-bar side panel ────────────────────────────────
  const sideProvider = new AiCodeSidePanelProvider(
    context.extensionUri,
    handleWebviewMessage
  );
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      AiCodeSidePanelProvider.viewType,
      sideProvider,
      { webviewOptions: { retainContextWhenHidden: true } }
    )
  );

  // ── Helper: open / reveal the standalone editor panel ───────────────────
  function openPanel() {
    const panel = AiCodePanel.createOrShow(context.extensionUri, handleWebviewMessage);
    messaging.registerPanel(panel);
    const ctx = getCodeContext();
    if (ctx) {
      messaging.send({ type: "setContext", payload: ctx });
    }
  }

  // ── Register all commands ───────────────────────────────────────────────
  const register = (cmd: string, fn: (...args: any[]) => any) =>
    context.subscriptions.push(vscode.commands.registerCommand(cmd, fn));

  register("aicode.openAssistant", () => openPanel());

  register("aicode.explainSelection", async () => {
    openPanel();
    await cmdExplainSelection();
  });

  register("aicode.explainFile", async () => {
    openPanel();
    await cmdExplainFile();
  });

  register("aicode.whyExists", async () => {
    openPanel();
    await cmdWhyExists();
  });

  register("aicode.showRelationships", async () => {
    openPanel();
    await cmdShowRelationships();
  });

  register("aicode.traceDataFlow", async () => {
    openPanel();
    await cmdTraceDataFlow();
  });

  register("aicode.showHistory", async () => {
    openPanel();
    await cmdShowHistory();
  });

  register("aicode.showImpact", async () => {
    openPanel();
    await cmdShowImpact();
  });

  register("aicode.findRelatedTests", async () => {
    openPanel();
    await cmdFindRelatedTests();
  });

  register("aicode.explainError", async () => {
    openPanel();
    await cmdExplainError();
  });

  // ── Keep webview context in sync with the active editor ─────────────────
  context.subscriptions.push(
    vscode.window.onDidChangeTextEditorSelection(() => {
      const ctx = getCodeContext();
      if (ctx) {
        messaging.send({ type: "setContext", payload: ctx });
      }
    })
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => {
      const ctx = getCodeContext();
      if (ctx) {
        messaging.send({ type: "setContext", payload: ctx });
      }
    })
  );
}

export function deactivate() {}
