import { useEffect } from "react";
import { onMessage, postMessage } from "../services/vscodeApi";
import { useAppStore } from "../store/appStore";
import type { ExtensionToWebviewMessage } from "../types";

/**
 * Listens to messages from the VS Code extension host and updates the store.
 * Call once at the root of the app.
 */
export function useExtensionBridge() {
  const store = useAppStore();

  useEffect(() => {
    // Tell the extension we are ready
    postMessage({ type: "ready" });

    const cleanup = onMessage((event: MessageEvent) => {
      const msg = event.data as ExtensionToWebviewMessage;
      if (!msg?.type) { return; }

      switch (msg.type) {
        case "setContext":
          store.setCodeContext(msg.payload);
          break;
        case "setTab":
          store.setActiveTab(msg.payload.tab);
          break;
        case "setExplanationMode":
          store.setExplanationMode(msg.payload.mode);
          break;
        case "loading":
          store.setLoading(msg.payload.tab);
          break;
        case "error":
          store.setError(msg.payload.tab, msg.payload.message);
          break;
        case "capability":
          store.setUnavailable(msg.payload.tab, msg.payload.message);
          break;
        case "explanationResult":
          store.setExplanation(msg.payload);
          break;
        case "whyResult":
          store.setWhy(msg.payload);
          break;
        case "relationsResult":
          store.setRelations(msg.payload);
          break;
        case "dataflowResult":
          store.setDataFlow(msg.payload);
          break;
        case "historyResult":
          store.setHistory(msg.payload);
          break;
        case "impactResult":
          store.setImpact(msg.payload);
          break;
        case "testsResult":
          store.setTests(msg.payload);
          break;
        case "debugResult":
          store.setDebug(msg.payload);
          break;
        case "architectureResult":
          store.setArchitecture(msg.payload);
          break;
        case "useMock":
          store.setUseMock(msg.payload.value);
          break;
      }
    });

    return cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
