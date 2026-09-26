import * as vscode from "vscode";
import { CodeContext } from "../types";

/**
 * Collects the current editor context: active file, selection, language.
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
