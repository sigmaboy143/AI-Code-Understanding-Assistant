import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { ExtensionToWebviewMessage, WebviewToExtensionMessage } from "../types";

/**
 * Manages the AI Code Understanding side panel (webview).
 */
export class AiCodePanel {
  public static currentPanel: AiCodePanel | undefined;
  private readonly _panel: vscode.WebviewPanel | vscode.WebviewView;
  private _disposables: vscode.Disposable[] = [];
  private _messageHandler?: (msg: WebviewToExtensionMessage) => void;

  // ── Factory for a standalone editor panel ──────────────────────────────────
  static createOrShow(
    extensionUri: vscode.Uri,
    onMessage: (msg: WebviewToExtensionMessage) => void
  ): AiCodePanel {
    const column = vscode.window.activeTextEditor
      ? vscode.ViewColumn.Beside
      : vscode.ViewColumn.One;

    if (AiCodePanel.currentPanel) {
      (AiCodePanel.currentPanel._panel as vscode.WebviewPanel).reveal(column);
      AiCodePanel.currentPanel._messageHandler = onMessage;
      return AiCodePanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      "aiCodePanel",
      "AI Code Understanding",
      column,
      {
        enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, "webview-ui", "dist")],
        retainContextWhenHidden: true,
      }
    );

    const instance = new AiCodePanel(panel, extensionUri, onMessage);
    AiCodePanel.currentPanel = instance;
    return instance;
  }

  constructor(
    panel: vscode.WebviewPanel | vscode.WebviewView,
    private readonly _extensionUri: vscode.Uri,
    onMessage: (msg: WebviewToExtensionMessage) => void
  ) {
    this._panel = panel;
    this._messageHandler = onMessage;
    this._panel.webview.html = this._getHtml(this._panel.webview);

    this._panel.webview.onDidReceiveMessage(
      (msg: WebviewToExtensionMessage) => this._messageHandler?.(msg),
      null,
      this._disposables
    );

    if ("onDidDispose" in this._panel) {
      this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    }
  }

  postMessage(msg: ExtensionToWebviewMessage) {
    this._panel.webview.postMessage(msg);
  }

  dispose() {
    AiCodePanel.currentPanel = undefined;
    if ("dispose" in this._panel) {
      (this._panel as vscode.WebviewPanel).dispose();
    }
    while (this._disposables.length) {
      this._disposables.pop()?.dispose();
    }
  }

  private _getHtml(webview: vscode.Webview): string {
    const distUri = vscode.Uri.joinPath(this._extensionUri, "webview-ui", "dist");
    const indexPath = path.join(distUri.fsPath, "index.html");

    // Serve built React app
    if (fs.existsSync(indexPath)) {
      let html = fs.readFileSync(indexPath, "utf8");
      // Rewrite asset paths to vscode-resource: URIs
      html = html.replace(/(src|href)="\/([^"]+)"/g, (_match, attr, p) => {
        const assetUri = webview.asWebviewUri(
          vscode.Uri.joinPath(distUri, p)
        );
        return `${attr}="${assetUri}"`;
      });
      return html;
    }

    // Fallback: inline loading placeholder (shown until webview-ui is built)
    const nonce = getNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
             style-src 'unsafe-inline';
             script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Code Understanding</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--vscode-editor-background, #1e1e1e);
      color: var(--vscode-editor-foreground, #d4d4d4);
      font-family: var(--vscode-font-family, system-ui, sans-serif);
      font-size: 13px;
      display: flex; align-items: center; justify-content: center;
      height: 100vh; flex-direction: column; gap: 16px;
    }
    .spinner {
      width: 36px; height: 36px;
      border: 3px solid transparent;
      border-top-color: var(--vscode-progressBar-background, #0e70c0);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    p { opacity: 0.6; font-size: 12px; }
  </style>
</head>
<body>
  <div class="spinner"></div>
  <p>Building AI Code Understanding UI…</p>
  <p>Run: <code>npm run build-webview</code></p>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    vscode.postMessage({ type: 'ready' });
  </script>
</body>
</html>`;
  }
}

// ── SidePanel provider (activity bar webview view) ───────────────────────────

export class AiCodeSidePanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "aicode.sidePanel";

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _onMessage: (msg: WebviewToExtensionMessage) => void
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _ctx: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this._extensionUri, "webview-ui", "dist"),
      ],
    };

    const panel = new AiCodePanel(
      webviewView,
      this._extensionUri,
      this._onMessage
    );

    // Expose postMessage on the side-panel view for the messaging service
    (webviewView as any)._aiPanel = panel;
  }
}

function getNonce() {
  let text = "";
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
