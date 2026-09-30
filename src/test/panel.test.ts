import * as assert from "assert";
import * as fs from "fs";
import * as http from "http";
import type { AddressInfo } from "net";
import * as path from "path";
import * as vscode from "vscode";
import { MessagingService } from "../messaging/MessagingService";
import { AiCodePanel } from "../panels/AiCodePanel";
import type { ExtensionToWebviewMessage } from "../types";

/**
 * Command → webview message flow, exercised in a real Extension Development
 * Host.
 *
 * The user-facing path this file covers is the whole chain a person triggers
 * from the palette: a command runs, the extension reads the editor, calls the
 * API layer, and posts messages to the panel. Nothing here is stubbed except
 * the backend itself, which is replaced by a real local HTTP server so the
 * actual axios transport, the X-Request-Id header and the response mapping are
 * all exercised rather than assumed.
 *
 * A stubbed `vscode` module could not catch any of that: it would test the
 * mocks instead of the extension.
 */

const EXTENSION_ROOT = path.resolve(__dirname, "..", "..");
const WEBVIEW_DIST = path.join(EXTENSION_ROOT, "webview-ui", "dist");

const SOURCE = [
  "export function add(a: number, b: number): number {",
  "  return a + b;",
  "}",
].join("\n");

/** The first line of SOURCE, used where only part of the file is selected. */
const FIRST_LINE = SOURCE.split("\n")[0];

const LONG_LINE = "const padding = '" + "x".repeat(120_000) + "';";

/** A body shaped exactly like the backend's AnalysisResult. */
const ANALYSIS_RESULT = {
  requestId: "server-correlation-id",
  language: "typescript",
  symbols: [],
  relationships: [],
  summary: "Adds two numbers and returns the sum.",
  confidence: {
    level: "unknown",
    model: "llama3",
    reasoning: "No retrieval evidence was available.",
  },
  evidence: [
    {
      kind: "source_code",
      sourceType: "source_code",
      detail: "the return statement",
      filePath: "Untitled-1",
      lineStart: 2,
      lineEnd: 2,
      chunkId: null,
    },
  ],
  analysedAt: "2026-01-01T00:00:00.000Z",
};

interface CapturedRequest {
  method: string;
  url: string;
  headers: http.IncomingHttpHeaders;
  body: Record<string, unknown> | undefined;
}

interface StubBackend {
  url: string;
  requests: CapturedRequest[];
  /** Stops listening and releases the port. */
  stop: () => Promise<void>;
}

/**
 * A real HTTP server standing in for the NestJS backend.
 *
 * Returning a genuine AnalysisResult (with a `confidence` the AI Engine could
 * actually produce) is what makes the mapping assertions meaningful: a fake
 * transport returning a hand-built UI object would prove nothing about the
 * adapter.
 */
async function startStubBackend(body: unknown = ANALYSIS_RESULT): Promise<StubBackend> {
  const requests: CapturedRequest[] = [];

  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      let parsed: Record<string, unknown> | undefined;
      try {
        parsed = raw.length > 0 ? JSON.parse(raw) : undefined;
      } catch {
        parsed = undefined;
      }
      requests.push({
        method: req.method ?? "",
        url: req.url ?? "",
        headers: req.headers,
        body: parsed,
      });

      res.writeHead(201, {
        "Content-Type": "application/json",
        // The backend echoes the caller's correlation ID; the extension prefers
        // the value it gets back over the one it sent.
        "X-Request-Id": String(req.headers["x-request-id"] ?? ""),
      });
      res.end(JSON.stringify(body));
    });
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;

  return {
    url: `http://127.0.0.1:${port}`,
    requests,
    stop: () =>
      new Promise<void>((resolve, reject) =>
        server.close((err) => (err ? reject(err) : resolve()))
      ),
  };
}

/** A port nothing is listening on, so a request to it is refused. */
async function reserveClosedPort(): Promise<number> {
  const server = http.createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  await new Promise<void>((resolve, reject) =>
    server.close((err) => (err ? reject(err) : resolve()))
  );
  return port;
}

function messagesOfType<T extends ExtensionToWebviewMessage["type"]>(
  sent: ExtensionToWebviewMessage[],
  type: T
): Array<Extract<ExtensionToWebviewMessage, { type: T }>> {
  return sent.filter(
    (msg): msg is Extract<ExtensionToWebviewMessage, { type: T }> =>
      msg.type === type
  );
}

/** Polls until `predicate` matches a message, so no arbitrary sleep is needed. */
async function waitFor(
  sent: ExtensionToWebviewMessage[],
  predicate: (msg: ExtensionToWebviewMessage) => boolean,
  description: string,
  timeoutMs = 20_000
): Promise<ExtensionToWebviewMessage> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const found = sent.find(predicate);
    if (found) {
      return found;
    }
    if (Date.now() > deadline) {
      assert.fail(
        `timed out after ${timeoutMs}ms waiting for ${description}. Saw: ${sent
          .map((m) => m.type)
          .join(", ")}`
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

async function openSourceDocument(
  content: string = SOURCE
): Promise<vscode.TextEditor> {
  const document = await vscode.workspace.openTextDocument({
    language: "typescript",
    content,
  });
  const editor = await vscode.window.showTextDocument(document);
  return editor;
}

function selectAll(editor: vscode.TextEditor): void {
  const lastLine = editor.document.lineCount - 1;
  editor.selection = new vscode.Selection(
    new vscode.Position(0, 0),
    editor.document.lineAt(lastLine).range.end
  );
}

async function setSetting(key: string, value: unknown): Promise<void> {
  await vscode.workspace
    .getConfiguration("aicode")
    .update(key, value, vscode.ConfigurationTarget.Global);
}

suite("Webview panel wiring", function () {
  // Creating a real webview, booting the React bundle and driving a command
  // all take longer than Mocha's 2s default, so the whole suite is given room.
  this.timeout(60_000);

  test("the built webview assets the panel loads exist", () => {
    // _getHtml() hard-codes assets/index.js and assets/index.css because the
    // Vite config emits flat names. If the build output ever changes shape the
    // panel would render a blank body with no error, so the files are checked.
    for (const asset of ["index.html", "assets/index.js", "assets/index.css"]) {
      assert.ok(
        fs.existsSync(path.join(WEBVIEW_DIST, asset)),
        `webview-ui/dist/${asset} is missing — run npm run build-webview`
      );
    }
  });

  test("openAssistant creates a panel that serves the built React app", async () => {
    await vscode.commands.executeCommand("aicode.openAssistant");

    const panel = AiCodePanel.currentPanel;
    assert.ok(panel, "aicode.openAssistant did not create a panel");

    // The webview handle is private; reading it is the only way to assert on
    // the HTML VS Code was actually given.
    const webview = (
      panel as unknown as { _panel: vscode.WebviewPanel }
    )._panel.webview;
    const html = webview.html;

    assert.ok(html.includes("assets/index.js"), "panel HTML does not load the bundle");
    assert.ok(html.includes("assets/index.css"), "panel HTML does not load the stylesheet");
    assert.ok(
      html.includes("Content-Security-Policy"),
      "panel HTML has no content security policy"
    );
    assert.ok(
      /nonce-[A-Za-z0-9]{32}/.test(html),
      "the bundle script tag is not covered by a nonce"
    );
    assert.ok(
      !html.includes("Building AI Code Understanding UI"),
      "the panel fell back to the 'not built yet' placeholder"
    );
  });

  test("the built panel announces itself to the extension", async () => {
    // The real React app posts { type: "ready" } on mount. If the bundle is
    // blocked by CSP or fails to load, this never arrives and every later
    // request would sit on a blank panel.
    await vscode.commands.executeCommand("aicode.openAssistant");

    const messaging = MessagingService.getInstance();
    const sent: ExtensionToWebviewMessage[] = [];
    const original = messaging.send.bind(messaging);
    messaging.send = (msg) => {
      sent.push(msg);
      return original(msg);
    };

    try {
      await vscode.commands.executeCommand("aicode.explainSelection");
      await waitFor(
        sent,
        (msg) => msg.type === "useMock",
        "the useMock broadcast that answers the webview's ready message"
      );
    } finally {
      messaging.send = original;
    }
  });
});

suite("Command to webview message flow", function () {
  this.timeout(60_000);

  let sent: ExtensionToWebviewMessage[] = [];
  let original: MessagingService["send"];
  let backend: StubBackend;

  suiteSetup(async () => {
    backend = await startStubBackend();
  });

  suiteTeardown(async () => {
    await backend.stop();
    await setSetting("backendUrl", "http://localhost:3000");
    await setSetting("useMockData", true);
  });

  setup(async () => {
    const messaging = MessagingService.getInstance();
    sent = [];
    original = messaging.send.bind(messaging);
    messaging.send = (msg) => {
      sent.push(msg);
      return original(msg);
    };
    // Every test starts from mock mode with the default backend URL; the live
    // tests opt in explicitly.
    await setSetting("useMockData", true);
    await setSetting("backendUrl", backend.url);
    await vscode.commands.executeCommand("workbench.action.closeAllEditors");
  });

  teardown(() => {
    MessagingService.getInstance().send = original;
    AiCodePanel.currentPanel?.dispose();
  });

  test("Explain Selected Code reports progress and a mock result", async () => {
    const editor = await openSourceDocument();
    selectAll(editor);

    await vscode.commands.executeCommand("aicode.explainSelection");

    const result = await waitFor(
      sent,
      (msg) => msg.type === "explanationResult",
      "an explanationResult for the explain tab"
    );

    // The tab is switched and a spinner is raised before the request, so the
    // panel never sits blank while a call is in flight.
    assert.ok(
      messagesOfType(sent, "setTab").some((m) => m.payload.tab === "explain"),
      "the command did not switch the panel to the Explain tab"
    );
    assert.ok(
      messagesOfType(sent, "loading").some((m) => m.payload.tab === "explain"),
      "no loading state was raised for the explain tab"
    );

    // The most recent context wins: showing a document also fires
    // onDidChangeActiveTextEditor, which broadcasts a context before the
    // selection has been made.
    const contexts = messagesOfType(sent, "setContext");
    const context = contexts[contexts.length - 1];
    assert.ok(context, "the editor context was never sent to the panel");
    assert.strictEqual(context.payload.language, "typescript");
    assert.strictEqual(context.payload.selectedText, SOURCE);

    if (result.type === "explanationResult") {
      assert.ok(result.payload.what.length > 0, "mock result carried no summary");
      assert.strictEqual(result.payload.source, undefined, "mock data must not claim source backend");
    }

    // Mock mode is documented as making no HTTP request at all.
    assert.strictEqual(backend.requests.length, 0);
  });

  test("mock mode is labelled as demo data, not as a backend result", async () => {
    const editor = await openSourceDocument();
    selectAll(editor);

    await vscode.commands.executeCommand("aicode.explainSelection");
    const result = await waitFor(
      sent,
      (msg) => msg.type === "explanationResult",
      "an explanationResult"
    );

    // The webview renders its "demo / mock mode" notice from this flag. If a
    // mock payload ever claimed source: "backend", demo output would be shown
    // as a real analysis.
    assert.notStrictEqual(
      result.type === "explanationResult" ? result.payload.source : "backend",
      "backend"
    );
    assert.ok(
      messagesOfType(sent, "useMock").some((m) => m.payload.value === true),
      "the panel was not told it is in mock mode"
    );
  });

  test("Explain Selected Code calls POST /analysis/code with the selection", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument();
    // Only the first line is selected, so the wire body proves the selection
    // was analysed rather than the whole document.
    editor.selection = new vscode.Selection(
      new vscode.Position(0, 0),
      editor.document.lineAt(0).range.end
    );

    const before = backend.requests.length;
    await vscode.commands.executeCommand("aicode.explainSelection");
    await waitFor(
      sent,
      (msg) => msg.type === "explanationResult" || msg.type === "error",
      "the analysis to settle"
    );

    assert.strictEqual(backend.requests.length, before + 1, "expected exactly one request");
    const request = backend.requests[backend.requests.length - 1];
    assert.strictEqual(request.method, "POST");
    assert.strictEqual(request.url, "/analysis/code");

    // The backend runs its ValidationPipe with forbidNonWhitelisted, so an
    // undeclared key is a 400 rather than a dropped field.
    assert.deepStrictEqual(
      Object.keys(request.body ?? {}).sort(),
      ["code", "filePath", "language"],
      "the request body must contain only declared AnalyzeCodeDto fields"
    );
    assert.strictEqual(request.body?.language, "typescript");
    assert.strictEqual(
      request.body?.code,
      FIRST_LINE,
      "the analysis subject must be the selection, not the whole file"
    );

    // Correlation is a real part of the contract: the backend honours an
    // inbound X-Request-Id and the panel shows whatever comes back.
    const sentId = request.headers["x-request-id"];
    assert.ok(
      typeof sentId === "string" && sentId.length > 0,
      "no X-Request-Id header was sent to the backend"
    );
    assert.match(
      String(sentId),
      /^[A-Za-z0-9._~-]{1,128}$/,
      "the generated correlation ID does not satisfy the backend's allowlist"
    );
  });

  test("a real analysis is mapped without inventing content", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument();
    selectAll(editor);

    await vscode.commands.executeCommand("aicode.explainSelection");
    const message = await waitFor(
      sent,
      (msg) => msg.type === "explanationResult",
      "the mapped backend result"
    );
    assert.strictEqual(message.type, "explanationResult");
    const payload = message.payload;

    assert.strictEqual(payload.source, "backend");
    assert.strictEqual(payload.what, ANALYSIS_RESULT.summary);
    // The backend returns one summary. Inventing a how/why split would assert
    // three separate findings the AI Engine never made.
    assert.strictEqual(payload.how, "");
    assert.strictEqual(payload.why, "");
    assert.strictEqual(payload.mode, "intermediate");

    // Confidence is carried, never upgraded, and a missing score stays missing
    // rather than becoming 0.
    assert.strictEqual(payload.confidence, "unknown");
    assert.strictEqual(payload.confidenceMeta?.level, "unknown");
    assert.strictEqual(payload.confidenceMeta?.model, "llama3");
    assert.strictEqual(payload.confidenceMeta?.score, undefined);
    assert.strictEqual(payload.requestId, "server-correlation-id");
    assert.strictEqual(payload.analysedAt, ANALYSIS_RESULT.analysedAt);

    assert.strictEqual(payload.evidence?.length, 1);
    const evidence = payload.evidence?.[0];
    assert.strictEqual(evidence?.sourceType, "source_code");
    assert.strictEqual(evidence?.filePath, "Untitled-1");
    assert.deepStrictEqual(evidence?.lines, [2, 2]);

    // Empty arrays are omitted rather than rendered as empty sections.
    assert.strictEqual(payload.symbols, undefined);
    assert.strictEqual(payload.relationships, undefined);
  });

  test("Explain File calls POST /analysis/file with the whole document", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument();
    editor.selection = new vscode.Selection(
      new vscode.Position(0, 0),
      new vscode.Position(0, 6)
    );

    const before = backend.requests.length;
    await vscode.commands.executeCommand("aicode.explainFile");
    await waitFor(
      sent,
      (msg) => msg.type === "explanationResult" || msg.type === "error",
      "the file analysis to settle"
    );

    const request = backend.requests[backend.requests.length - 1];
    assert.ok(
      backend.requests.length > before,
      "Explain File issued no request"
    );
    assert.strictEqual(request.url, "/analysis/file");
    // Sending the selection here would still return 201 — it would just be a
    // 201 for the wrong thing.
    assert.strictEqual(
      request.body?.code,
      SOURCE,
      "Explain File must send the complete document, not the selection"
    );
    assert.ok(
      typeof request.body?.filePath === "string" &&
        (request.body?.filePath as string).length > 0,
      "AnalyzeFileDto requires a non-empty filePath"
    );
  });

  test("a backend feature with no route reports a capability notice, not an error", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument();
    selectAll(editor);

    const before = backend.requests.length;
    await vscode.commands.executeCommand("aicode.whyExists");

    const capability = await waitFor(
      sent,
      (msg) => msg.type === "capability",
      "a capability notice for the Why tab"
    );
    assert.strictEqual(capability.type, "capability");
    assert.strictEqual(capability.payload.tab, "why");
    assert.strictEqual(capability.payload.capability, "why");
    assert.ok(
      capability.payload.message.includes("aicode.useMockData"),
      "the notice should tell the user how to explore the demo"
    );
    assert.strictEqual(
      messagesOfType(sent, "error").length,
      0,
      "a missing backend feature must never be reported as a failed request"
    );
    assert.strictEqual(
      backend.requests.length,
      before,
      "no request may be sent to a route the backend does not define"
    );
  });

  test("an unreachable backend is reported as an error, not a hang", async () => {
    const closedPort = await reserveClosedPort();
    await setSetting("useMockData", false);
    await setSetting("backendUrl", `http://127.0.0.1:${closedPort}`);
    const editor = await openSourceDocument();
    selectAll(editor);

    await vscode.commands.executeCommand("aicode.explainSelection");

    const error = await waitFor(
      sent,
      (msg) => msg.type === "error",
      "an error state for the explain tab"
    );
    assert.strictEqual(error.type, "error");
    assert.strictEqual(error.payload.tab, "explain");
    assert.ok(
      error.payload.message.includes("Could not reach the backend"),
      `expected an actionable connection message, got: ${error.payload.message}`
    );
  });

  test("an oversized selection is refused before a request is sent", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument(`${SOURCE}\n${LONG_LINE}`);
    selectAll(editor);

    const before = backend.requests.length;
    await vscode.commands.executeCommand("aicode.explainSelection");

    const error = await waitFor(
      sent,
      (msg) => msg.type === "error",
      "the oversize guard message"
    );
    assert.strictEqual(error.type, "error");
    assert.ok(
      error.payload.message.includes("100,000"),
      `expected the limit to be named in the message, got: ${error.payload.message}`
    );
    // The backend caps code at 100000 characters and would answer 400; the
    // guard exists so the user is told while the document is still in front of
    // them, and so no oversized payload is put on the wire.
    assert.strictEqual(backend.requests.length, before);
  });

  test("Explain Selected Code without a selection sends no request", async () => {
    await setSetting("useMockData", false);
    const editor = await openSourceDocument();
    editor.selection = new vscode.Selection(0, 0, 0, 0);

    const before = backend.requests.length;
    await vscode.commands.executeCommand("aicode.explainSelection");

    assert.strictEqual(
      messagesOfType(sent, "explanationResult").length,
      0,
      "an analysis ran without a selection"
    );
    assert.strictEqual(
      backend.requests.length,
      before,
      "no request may be sent when the user has selected nothing"
    );
  });
});
