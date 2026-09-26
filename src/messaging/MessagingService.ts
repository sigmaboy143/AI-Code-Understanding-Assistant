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
  private _panel: AiCodePanel | undefined;

  static getInstance(): MessagingService {
    if (!MessagingService._instance) {
      MessagingService._instance = new MessagingService();
    }
    return MessagingService._instance;
  }

  registerPanel(panel: AiCodePanel) {
    this._panel = panel;
  }

  unregisterPanel() {
    this._panel = undefined;
  }

  /** Send a message to the webview. */
  send(msg: ExtensionToWebviewMessage) {
    this._panel?.postMessage(msg);
  }

  /** Handle infrastructure messages received FROM the webview (navigate, ready). */
  async handle(msg: WebviewToExtensionMessage) {
    switch (msg.type) {
      case "ready": {
        const config = vscode.workspace.getConfiguration("aicode");
        const useMock = config.get<boolean>("useMockData", true);
        const ctx = getCodeContext();
        if (ctx) {
          this.send({ type: "setContext", payload: ctx });
        }
        this.send({ type: "useMock", payload: { value: useMock } });
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
}
