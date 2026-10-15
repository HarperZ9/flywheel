// Loads extension.js against a fake `vscode` module and prints what it did as
// JSON lines. Used by tests/test_vscode_extension.py; needs only Node.
'use strict';
const Module = require('module');
const path = require('path');
const sent = [], created = [], registered = {};
let inputAnswer = 'what does this do?';
const fakeTerminal = (opts) => ({opts, exitStatus: undefined, sendText: (t) => sent.push(t), show() {}});
const vscode = {
  workspace: {
    getConfiguration: () => ({get: (k) => ({command: 'flywheel', mode: 'edit', extraArgs: ['--backend', 'claude']})[k]}),
    getWorkspaceFolder: () => ({uri: {fsPath: path.resolve('/proj')}}),
    workspaceFolders: [{uri: {fsPath: path.resolve('/proj')}}],
  },
  window: {
    activeTextEditor: {document: {uri: {fsPath: path.resolve('/proj/src/a b.py')}},
                       selection: {isEmpty: false, start: {line: 9}, end: {line: 19}}},
    createTerminal: (o) => { created.push(o); return fakeTerminal(o); },
    showInputBox: async () => inputAnswer,
    showInformationMessage: () => {},
    onDidCloseTerminal: () => ({dispose() {}}),
  },
  commands: {registerCommand: (id, fn) => { registered[id] = fn; return {dispose() {}}; }},
};
const orig = Module._load;
Module._load = function (request, ...rest) { return request === 'vscode' ? vscode : orig.call(this, request, ...rest); };
const ext = require(path.join(__dirname, '..', 'extension.js'));
(async () => {
  ext.activate({subscriptions: []});
  await registered['flywheel.start']();
  await registered['flywheel.askSelection']();
  console.log(JSON.stringify({registered: Object.keys(registered).sort(), sent, created: created.length}));
})();
