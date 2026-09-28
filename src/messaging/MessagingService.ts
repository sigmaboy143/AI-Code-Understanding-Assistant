import * as vscode from "vscode";
import { ExtensionToWebviewMessage, WebviewToExtensionMessage } from "../types";
import { getCodeContext } from "../context/contextCollector";
import { AiCodePanel } from "../panels/AiCodePanel";

/**
 * Central message bus between the extension host and any active webview panel.
 * The panel registers itself here; commands post to it.
 */
export class MessagingService {
  private static _instance: MessagingService;
  /** Side panel (activity bar WebviewView) — registered once on activation */
  private _sidePanel: AiCodePanel | undefined;
  /** Editor panel (standalone WebviewPanel) — registered when openAssistant command runs */
  private _editorPanel: AiCodePanel | undefined;

  static getInstance(): MessagingService {
    if (!MessagingService._instance) {
      MessagingService._instance = new MessagingService();
    }
    return MessagingService._instance;
  }

  /** Register the activity-bar side-panel (WebviewView). */
  registerSidePanel(panel: AiCodePanel) {
    this._sidePanel = panel;
  }

  /** Register the standalone editor panel (WebviewPanel). */
  registerPanel(panel: AiCodePanel) {
    this._editorPanel = panel;
  }

  unregisterPanel() {
    this._editorPanel = undefined;
  }

  /** Send a message to all active webview panels. */
  send(msg: ExtensionToWebviewMessage) {
    this._sidePanel?.postMessage(msg);
    this._editorPanel?.postMessage(msg);
  }

  /** Handle infrastructure messages received FROM the webview (navigate, ready). */
  async handle(msg: WebviewToExtensionMessage) {
    switch (msg.type) {
      case "ready": {
        const ctx = getCodeContext();
        if (ctx) {
          this.send({ type: "setContext", payload: ctx });
        }
        this.broadcastMode();
        break;
      }

      case "navigate": {
        const { file, line } = msg.payload;
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) {
          break;
        }
        const uri = vscode.Uri.joinPath(workspaceFolders[0].uri, file);
        try {
          const doc = await vscode.workspace.openTextDocument(uri);
          const pos = line ? new vscode.Position(line - 1, 0) : undefined;
          await vscode.window.showTextDocument(doc, {
            selection: pos ? new vscode.Selection(pos, pos) : undefined,
          });
        } catch {
          vscode.window.showErrorMessage(`Cannot open file: ${file}`);
        }
        break;
      }

      default:
        break;
    }
  }

  /**
   * Tells the webview whether it is showing mock or real data.
   *
   * Re-broadcast on configuration change as well as on `ready`, so toggling
   * `aicode.useMockData` updates the panel's mode badge immediately instead of
   * leaving a stale "MOCK" marker over live backend results.
   */
  broadcastMode() {
    const config = vscode.workspace.getConfiguration("aicode");
    this.send({ type: "useMock", payload: { value: config.get<boolean>("useMockData", true) } });
  }

  /** Subscribes to configuration changes. Returns a disposable for activation. */
  watchConfiguration(onChange: (e: vscode.ConfigurationChangeEvent) => void) {
    return vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("aicode.useMockData")) {
        this.broadcastMode();
      }
      onChange(e);
    });
  }
}
