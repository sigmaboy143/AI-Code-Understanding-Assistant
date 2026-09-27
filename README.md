# AI Code Understanding Assistant

A VS Code extension that explains selected code and whole files, and surfaces the
confidence and evidence behind each answer. The extension is the only client of
the backend; the backend is the only caller of the AI Engine.

## Features

- **Explain Selected Code** — analyses the current selection via `POST /analysis/code`
- **Explain File** — analyses the complete active document via `POST /analysis/file`
- **Relations** — resolves relationships for a file via `GET /relationships`
- Activity Bar side panel plus a standalone editor panel
- Confidence and evidence rendered from the backend's own values, never invented

### Panel tabs: real vs mock

The backend currently implements only a few features. The other tabs are kept in
the UI as clearly-labelled placeholders rather than being removed, and they never
issue a request to a URL that does not exist.

| Tab | Real backend | Endpoint | Notes |
| --- | --- | --- | --- |
| Explain | Yes | `POST /analysis/code`, `POST /analysis/file` | Real result when mock mode is off |
| Relations | Yes | `GET /relationships?filePath&language` | Route is real; the backend's resolver currently returns an empty array |
| Why | No | — | Backend capability not currently available |
| Data | No | — | Backend capability not currently available |
| History | No | — | Backend capability not currently available |
| Impact | No | — | Backend capability not currently available |
| Tests | No | — | Backend capability not currently available |
| Debug | No | — | Backend capability not currently available |
| Arch | No | — | Backend capability not currently available |
| Search | No | — | Demo only; results are fixed strings, not real matches |
| Chat | No | — | Demo only; replies are placeholders, not analysis |

"Backend capability not currently available" is not an error state. Nothing was
requested and nothing failed — the feature simply has no HTTP route yet. The
`conversations`, `tests`, `documentation`, `onboarding`, `auth`, `users`,
`organizations`, `projects` and `repositories` controllers are declared in the
backend but declare no route handler, and impact / debugging / architecture / git
exist only as injectable services with no controller.

## Requirements

- VS Code `^1.138.0`
- For real (non-mock) mode: the NestJS backend running and reachable. The
  extension never calls an AI provider directly.

## Extension Settings

This extension contributes the following settings:

* `aicode.useMockData` — when `true` (the default) every tab returns locally
  generated demo data and no HTTP request is made. Set it to `false` to talk to
  the real backend.
* `aicode.backendUrl` — base URL of the backend. Defaults to
  `http://localhost:3000`. A trailing slash is tolerated.
* `aicode.explanationMode` — default explanation depth: `beginner`,
  `intermediate` or `advanced`.

### Running the extension

```bash
npm install
npm run build-webview   # builds the React webview into webview-ui/dist
npm run compile         # compiles the extension host to out/
```

Then press <kbd>F5</kbd> to launch an Extension Development Host.

To run the webview in a plain browser for UI work:

```bash
npm run watch-webview
```

Outside VS Code there is no extension host, so no backend call can be made; the
webview logs outgoing messages to the console instead.

### Tests

```bash
npm run test:unit       # contract/adapter unit tests, no VS Code required
npm test                # extension-host tests (downloads VS Code on first run)
```

### Correlation

Each real request carries an `X-Request-Id` header. The backend's correlation
middleware honours it and always echoes one back, so the ID shown under an
Explain result is the backend's own correlation ID and can be quoted when
reporting a problem.

## Known Issues

- Every tab other than Explain and Relations is a placeholder, for the reasons
  in the table above. They are not wired to the backend because no endpoint
  exists to wire them to.
- `GET /relationships` is real but its service resolves to an empty array, so
  the Relations tab legitimately shows "no relationships" against a live backend.
- A real analysis returns one `summary`. The What / How / Why sections remain in
  the panel, but How and Why state that the backend did not provide them rather
  than being filled with generated prose.
- The backend caps `code` at 100000 characters. Selecting more than that is
  reported before the request is sent.

## Release Notes

Users appreciate release notes as you update your extension.

### 1.0.0

Initial release of ...

### 1.0.1

Fixed issue #.

### 1.1.0

Added features X, Y, and Z.

---

## Following extension guidelines

Ensure that you've read through the extensions guidelines and follow the best practices for creating your extension.

* [Extension Guidelines](https://code.visualstudio.com/api/references/extension-guidelines)

## Working with Markdown

You can author your README using Visual Studio Code. Here are some useful editor keyboard shortcuts:

* Split the editor (`Cmd+\` on macOS or `Ctrl+\` on Windows and Linux).
* Toggle preview (`Shift+Cmd+V` on macOS or `Shift+Ctrl+V` on Windows and Linux).
* Press `Ctrl+Space` (Windows, Linux, macOS) to see a list of Markdown snippets.

## For more information

* [Visual Studio Code's Markdown Support](http://code.visualstudio.com/docs/languages/markdown)
* [Markdown Syntax Reference](https://help.github.com/articles/markdown-basics/)

**Enjoy!**
