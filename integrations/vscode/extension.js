// Flywheel for VS Code: starts `flywheel code` in an integrated terminal in the
// workspace folder, and sends requests that name the current file or selection.
// The session itself (permissions, sandbox, ledger) is the flywheel command's;
// this extension only opens it and types into it. No dependencies.
'use strict';
const vscode = require('vscode');
const path = require('path');

let terminal = null;

function settings() {
  const c = vscode.workspace.getConfiguration('flywheel');
  return {command: c.get('command') || 'flywheel', mode: c.get('mode') || 'ask',
          extra: c.get('extraArgs') || []};
}

function quote(arg) {
  return /^[\w@%+=:,./-]+$/.test(arg) ? arg : JSON.stringify(arg);
}

function folder() {
  const editor = vscode.window.activeTextEditor;
  const ws = editor && vscode.workspace.getWorkspaceFolder(editor.document.uri);
  return (ws || (vscode.workspace.workspaceFolders || [])[0] || {}).uri;
}

function session(extraArgs) {
  if (terminal && terminal.exitStatus === undefined) {
    terminal.show();
    return terminal;
  }
  const s = settings();
  const cwd = folder();
  terminal = vscode.window.createTerminal({name: 'Flywheel', cwd: cwd ? cwd.fsPath : undefined});
  const args = ['code', '--mode', s.mode, ...s.extra, ...(extraArgs || [])];
  terminal.sendText([s.command, ...args].map(quote).join(' '));
  terminal.show();
  return terminal;
}

function relative(uri) {
  const root = folder();
  return root ? path.relative(root.fsPath, uri.fsPath).split(path.sep).join('/') : uri.fsPath;
}

async function ask(withSelection) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showInformationMessage('Open a file first.');
    return;
  }
  const rel = relative(editor.document.uri);
  let where = `@${rel}`;
  if (withSelection && !editor.selection.isEmpty) {
    const a = editor.selection.start.line + 1, b = editor.selection.end.line + 1;
    where += ` (lines ${a} to ${b})`;
  }
  const question = await vscode.window.showInputBox({prompt: `Ask Flywheel about ${where}`});
  if (!question) return;
  session().sendText(`${question} ${where}`.replace(/\r?\n/g, ' '));
}

function activate(context) {
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg('flywheel.start', () => session());
  reg('flywheel.continue', () => session(['--continue']));
  reg('flywheel.askFile', () => ask(false));
  reg('flywheel.askSelection', () => ask(true));
  reg('flywheel.doctor', () => {
    const t = vscode.window.createTerminal({name: 'Flywheel doctor'});
    t.sendText(`${quote(settings().command)} doctor`);
    t.show();
  });
  context.subscriptions.push(vscode.window.onDidCloseTerminal(t => {
    if (t === terminal) terminal = null;
  }));
}

function deactivate() {}

module.exports = {activate, deactivate};
