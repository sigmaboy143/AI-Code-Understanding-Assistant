import * as vscode from "vscode";
import { CodeContext } from "../types";
import { BACKEND_MAX_CODE_LENGTH } from "../types/backend";

/**
 * Collects the current editor context: active file, selection, language.
 *
 * The selection fields are only populated when there is a selection. This stays
 * lean on purpose: it is broadcast to the webview on every cursor move, so it
 * must never carry whole-file text. Full-document reads are explicit, via
 * resolveAnalysisCode / getActiveDocumentText.
 */
export function getCodeContext(): CodeContext | null {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return null;
  }

  const document = editor.document;
  const selection = editor.selection;
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  const file = vscode.workspace.asRelativePath(document.uri);

  const ctx: CodeContext = {
    file,
    language: document.languageId,
    workspaceRoot,
  };

  if (!selection.isEmpty) {
    ctx.selectedText = document.getText(selection);
    ctx.startLine = selection.start.line + 1;
    ctx.endLine = selection.end.line + 1;
  }

  return ctx;
}

/**
 * Returns the COMPLETE text of the active document.
 *
 * This is what POST /analysis/file requires as its `code` field. The backend
 * distinguishes that route from /analysis/code precisely because it expects the
 * whole file, so passing a selection here would silently analyse the wrong
 * thing while still returning a 201.
 */
export function getActiveDocumentText(): string | null {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return null;
  }
  return editor.document.getText();
}

/**
 * Picks the source text to send for an analysis request.
 *
 * With a selection, the selection is the analysis subject. Without one, the
 * full document is the only thing that can be analysed, so it is read here
 * rather than by the API layer — the document is only available in the
 * extension host.
 *
 * `requireFullDocument` forces the whole-file read even when a selection
 * exists, which is what the "Explain File" command needs.
 */
export function resolveAnalysisCode(
  ctx: CodeContext,
  requireFullDocument = false
): string {
  if (requireFullDocument) {
    const full = getActiveDocumentText();
    if (full === null) {
      throw new Error("No active document to analyze. Open a file in the editor first.");
    }
    return full;
  }

  if (ctx.selectedText) {
    return ctx.selectedText;
  }

  const full = getActiveDocumentText();
  if (full === null) {
    throw new Error("No active document to analyze. Open a file in the editor first.");
  }
  return full;
}

/**
 * The backend rejects a `code` field that is blank or longer than 100000
 * characters, so the oversize case is reported here — where the offending
 * document is still in front of the user — instead of as an opaque 400.
 */
export function assertCodeWithinBackendLimit(code: string): void {
  if (code.length > BACKEND_MAX_CODE_LENGTH) {
    throw new Error(
      `Selected code is ${code.length.toLocaleString("en-US")} characters, which exceeds the ` +
        `backend limit of ${BACKEND_MAX_CODE_LENGTH.toLocaleString("en-US")}. ` +
        `Select a smaller region and try again.`
    );
  }
}
