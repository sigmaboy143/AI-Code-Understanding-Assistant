/**
 * VS Code API bridge — works in both extension webview context and browser dev mode.
 */

declare function acquireVsCodeApi(): {
  postMessage(msg: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
};

type VsCodeApi = ReturnType<typeof acquireVsCodeApi>;

let _api: VsCodeApi | null = null;

function getVsCodeApi(): VsCodeApi | null {
  if (typeof acquireVsCodeApi !== "undefined") {
    if (!_api) {
      _api = acquireVsCodeApi();
    }
    return _api;
  }
  return null;
}

export function postMessage(msg: object) {
  const api = getVsCodeApi();
  if (api) {
    api.postMessage(msg);
  } else {
    // Browser dev mode — log to console
    console.log("[webview→extension]", msg);
  }
}

export function onMessage(handler: (event: MessageEvent) => void) {
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
