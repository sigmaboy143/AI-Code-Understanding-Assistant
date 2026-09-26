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
import { WebviewToExtensionMessage } from "./types";

export function activate(context: vscode.ExtensionContext) {
  console.log("AI Code Understanding Assistant activated");

  const messaging = MessagingService.getInstance();

  // ── Webview message handler ──────────────────────────────────────────────
  async function handleWebviewMessage(msg: WebviewToExtensionMessage) {
    await messaging.handle(msg, context);

    const ctx = getCodeContext();

    switch (msg.type) {
      case "requestExplain": {
        const result = await api.explainCode(msg.payload.context, msg.payload.mode);
        messaging.send({ type: "explanationResult", payload: result });
        break;
      }
      case "requestWhy": {
        const result = await api.explainWhy(msg.payload.context);
        messaging.send({ type: "whyResult", payload: result });
        break;
      }
      case "requestRelations": {
        const result = await api.getRelations(msg.payload.context);
        messaging.send({ type: "relationsResult", payload: result });
        break;
      }
      case "requestDataFlow": {
        const result = await api.traceDataFlow(msg.payload.context);
        messaging.send({ type: "dataflowResult", payload: result });
        break;
      }
      case "requestHistory": {
        const result = await api.getHistory(msg.payload.context);
        messaging.send({ type: "historyResult", payload: result });
        break;
      }
      case "requestImpact": {
        const result = await api.analyzeImpact(msg.payload.context);
        messaging.send({ type: "impactResult", payload: result });
        break;
      }
      case "requestTests": {
        const result = await api.findTests(msg.payload.context);
        messaging.send({ type: "testsResult", payload: result });
        break;
      }
      case "requestDebug": {
        const result = await api.debugError(msg.payload.context, msg.payload.error);
        messaging.send({ type: "debugResult", payload: result });
        break;
      }
      case "requestArchitecture": {
        const result = await api.getArchitecture(msg.payload.repositoryId);
        messaging.send({ type: "architectureResult", payload: result });
        break;
      }
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

  // ── Helper: open the panel ───────────────────────────────────────────────
  function openPanel() {
    const panel = AiCodePanel.createOrShow(context.extensionUri, handleWebviewMessage);
    messaging.registerPanel(panel);
    const ctx = getCodeContext();
    if (ctx) {
      messaging.send({ type: "setContext", payload: ctx });
    }
  }

  // ── Register commands ───────────────────────────────────────────────────
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

  // ── Track editor selection changes → keep webview context current ────────
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
