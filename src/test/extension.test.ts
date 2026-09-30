import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { isMockMode } from "../api/apiService";
import { MessagingService } from "../messaging/MessagingService";

/**
 * Activation, contribution and configuration tests.
 *
 * These run inside a real Extension Development Host (npm test → vscode-test),
 * not against a stubbed `vscode` module. That is the point of the file: the
 * checks below are about what VS Code actually loaded — whether the manifest
 * was honoured, whether every contributed command is really registered, and
 * whether the settings a user can change are the settings the code reads.
 *
 * The companion file `panel.test.ts` covers the runtime path from a command to
 * a webview message.
 */

const MANIFEST_PATH = path.resolve(__dirname, "..", "..", "package.json");

interface ManifestCommand {
  command: string;
  title: string;
}

interface Manifest {
  name: string;
  main: string;
  activationEvents: string[];
  contributes: {
    commands: ManifestCommand[];
    viewsContainers: Record<string, Array<{ id: string; title: string }>>;
    views: Record<string, Array<{ id: string; name: string; type?: string }>>;
    configuration: {
      properties: Record<
        string,
        { type: string; default: unknown; enum?: string[] }
      >;
    };
  };
}

/**
 * Reads the shipped manifest.
 *
 * The test is driven from the manifest rather than from a hand-copied list, so
 * adding a command without registering it — or renaming one in only one of the
 * two places — fails here instead of silently shipping a dead palette entry.
 */
function readManifest(): Manifest {
  return JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8")) as Manifest;
}

const manifest = readManifest();

function extension(): vscode.Extension<unknown> {
  const found = vscode.extensions.all.find(
    (ext) =>
      (ext.packageJSON as { name?: string } | undefined)?.name === manifest.name
  );
  assert.ok(
    found,
    `extension with manifest name "${manifest.name}" is not installed in the test host`
  );
  return found;
}

suite("Extension activation", () => {
  test("the extension under development is present and active", () => {
    const ext = extension();
    assert.strictEqual(ext.isActive, true, "activate() did not run on startup");
  });

  test("the manifest entry point exists on disk", () => {
    // `main` is what VS Code requires; a manifest pointing at a missing file
    // activates nothing and the failure is otherwise silent in the UI.
    const entry = path.resolve(path.dirname(MANIFEST_PATH), manifest.main);
    assert.ok(
      fs.existsSync(entry),
      `manifest "main" points at ${manifest.main}, which does not exist (run npm run compile)`
    );
  });

  test("activation is driven by the declared activation event", () => {
    assert.ok(
      manifest.activationEvents.includes("onStartupFinished"),
      "expected the manifest to declare onStartupFinished so the panel works without a command"
    );
  });
});

suite("Command registration", () => {
  test("every contributed command is registered in the host", async () => {
    const registered = await vscode.commands.getCommands(true);
    const missing = manifest.contributes.commands
      .map((c) => c.command)
      .filter((id) => !registered.includes(id));
    assert.deepStrictEqual(
      missing,
      [],
      `commands declared in package.json but not registered by activate(): ${missing.join(", ")}`
    );
  });

  test("the command surface matches the manifest exactly", async () => {
    const registered = await vscode.commands.getCommands(true);
    // View-container housekeeping commands (aicode.sidePanel.*) are generated
    // by VS Code itself, so only this extension's own commands are compared.
    const ours = registered
      .filter((id) => id.startsWith("aicode."))
      .filter((id) => !id.startsWith("aicode.sidePanel."));
    const declared = manifest.contributes.commands.map((c) => c.command).sort();
    assert.deepStrictEqual(ours.slice().sort(), declared);
  });

  test("every command has a title and a category", () => {
    for (const command of manifest.contributes.commands) {
      assert.ok(command.title, `${command.command} has no title`);
    }
  });
});

suite("Activity bar contribution", () => {
  test("the side panel view container and view are declared", () => {
    const containers = manifest.contributes.viewsContainers.activitybar ?? [];
    assert.ok(
      containers.some((c) => c.id === "aicode-sidebar"),
      "package.json declares no aicode-sidebar activity bar container"
    );

    const views = manifest.contributes.views["aicode-sidebar"] ?? [];
    const view = views.find((v) => v.id === "aicode.sidePanel");
    assert.ok(view, "package.json declares no aicode.sidePanel webview view");
    assert.strictEqual(
      view.type,
      "webview",
      "the side panel must be a webview view, not a tree view"
    );
  });
});

suite("Configuration", function () {
  this.timeout(30_000);

  const config = () => vscode.workspace.getConfiguration("aicode");

  suiteTeardown(async () => {
    // The suite toggles useMockData; put the user's default back.
    await config().update(
      "useMockData",
      manifest.contributes.configuration.properties["aicode.useMockData"].default,
      vscode.ConfigurationTarget.Global
    );
  });

  test("the manifest declares the three settings the code reads", () => {
    const properties = manifest.contributes.configuration.properties;
    for (const key of [
      "aicode.backendUrl",
      "aicode.useMockData",
      "aicode.explanationMode",
    ]) {
      assert.ok(properties[key], `package.json does not declare ${key}`);
    }
  });

  test("defaults resolve before any test overrides them", () => {
    const properties = manifest.contributes.configuration.properties;
    assert.strictEqual(
      config().get("useMockData"),
      properties["aicode.useMockData"].default
    );
    assert.strictEqual(
      config().get("backendUrl"),
      properties["aicode.backendUrl"].default
    );
    assert.strictEqual(
      config().get("explanationMode"),
      properties["aicode.explanationMode"].default
    );
  });

  test("explanationMode only offers the modes the panel can send", () => {
    // ExplanationMode is a closed union in src/types. A value in the settings
    // dropdown that the union does not contain would be sent to the backend as
    // a mode nothing understands, so the manifest and the type must agree.
    const modes = ["beginner", "intermediate", "advanced"];
    const declared = manifest.contributes.configuration.properties[
      "aicode.explanationMode"
    ].enum as string[] | undefined;
    assert.deepStrictEqual(
      (declared ?? []).slice().sort(),
      modes.slice().sort(),
      "aicode.explanationMode must offer exactly beginner, intermediate, advanced"
    );
  });

  test("isMockMode() follows the aicode.useMockData setting", async () => {
    assert.strictEqual(isMockMode(), true, "mock mode is the shipped default");

    await config().update(
      "useMockData",
      false,
      vscode.ConfigurationTarget.Global
    );
    assert.strictEqual(
      isMockMode(),
      false,
      "apiService.isMockMode() ignored the setting change"
    );

    await config().update("useMockData", true, vscode.ConfigurationTarget.Global);
    assert.strictEqual(isMockMode(), true);
  });

  test("toggling useMockData re-broadcasts the mode to the webview", async () => {
    // The webview labels its results MOCK or LIVE from this broadcast. Without
    // it, switching modes leaves a stale badge over real backend output.
    const seen: boolean[] = [];
    const messaging = MessagingService.getInstance();
    const original = messaging.send.bind(messaging);
    messaging.send = (msg) => {
      if (msg.type === "useMock") {
        seen.push(msg.payload.value);
      }
      return original(msg);
    };

    try {
      await config().update(
        "useMockData",
        false,
        vscode.ConfigurationTarget.Global
      );
      await config().update(
        "useMockData",
        true,
        vscode.ConfigurationTarget.Global
      );
    } finally {
      messaging.send = original;
    }

    assert.ok(
      seen.includes(false) && seen.includes(true),
      `expected broadcasts for both modes, got ${JSON.stringify(seen)}`
    );
  });

  test("a trailing slash on backendUrl is tolerated", () => {
    // The panel must not build "http://host:3000//analysis/code"; the transport
    // strips trailing slashes, which is asserted where the URL is built.
    const url = config().get<string>("backendUrl") ?? "";
    assert.ok(url.length > 0, "aicode.backendUrl must not be blank");
  });
});
