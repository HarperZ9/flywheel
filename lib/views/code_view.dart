// code_view.dart — the Code view: an IDE lane on the one surface. Open a
// folder, edit with highlighting and Ctrl+S, and put the gated agent to
// work on the workspace itself. The editor is local dart:io; the agent
// runs through the engine with the workspace as its sandbox root.

import 'dart:io';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../ide/agent_panel.dart';
import '../ide/editor_pane.dart';
import '../ide/file_tree.dart';
import '../ide/highlighter.dart';
import '../ide/workspace.dart' as ws;
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../ide/open_panel.dart';
import '../widgets/fw.dart';

class CodeView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const CodeView(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});

  @override
  State<CodeView> createState() => _CodeViewState();
}

class _CodeViewState extends State<CodeView> {
  String? _root;
  final List<OpenFile> _open = [];
  int _active = -1;
  String? _status;

  @override
  void dispose() {
    for (final f in _open) {
      f.controller.dispose();
    }
    super.dispose();
  }

  void _openWorkspace(String path) {
    final dir = Directory(path.trim());
    if (!dir.existsSync()) {
      setState(() => _status = 'Not a directory: ${path.trim()}');
      return;
    }
    widget.settings.rememberWorkspace(dir.path);
    setState(() {
      _root = dir.path;
      _open.clear();
      _active = -1;
      _status = null;
    });
  }

  void _openFile(String path) {
    final existing = _open.indexWhere((f) => f.path == path);
    if (existing >= 0) {
      setState(() => _active = existing);
      return;
    }
    final loaded = ws.loadFile(path);
    final file = OpenFile(
      path: path,
      controller: CodeEditingController(
          text: loaded.content, language: languageFor(path)),
      readOnly: loaded.readOnly,
      note: loaded.note,
    );
    setState(() {
      _open.add(file);
      _active = _open.length - 1;
    });
  }

  void _closeFile(int i) {
    setState(() {
      _open.removeAt(i).controller.dispose();
      if (_active >= _open.length) _active = _open.length - 1;
    });
  }

  void _save(OpenFile f) {
    if (f.readOnly) return;
    try {
      ws.saveFile(f.path, f.controller.text);
      setState(() {
        f.dirty = false;
        _status = 'saved ${f.name}';
      });
    } catch (e) {
      setState(() => _status = 'save failed: $e');
    }
  }

  /// After an agent run: reload every clean open file from disk so the
  /// editor shows what the agent actually wrote. Dirty files are kept and
  /// flagged rather than silently overwritten.
  void _reloadCleanFiles() {
    var reloaded = 0;
    for (final f in _open) {
      if (f.dirty || f.readOnly) continue;
      final fresh = ws.loadFile(f.path);
      if (fresh.content != f.controller.text) {
        f.controller.text = fresh.content;
        reloaded++;
      }
    }
    if (reloaded > 0) {
      setState(() => _status = '$reloaded open file(s) changed on disk, reloaded');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_root == null) {
      return OpenWorkspacePanel(
          settings: widget.settings, onOpen: _openWorkspace, status: _status);
    }
    final t = context.fw;
    final active = _active >= 0 && _active < _open.length ? _open[_active] : null;
    return Row(
      children: [
        Container(
          width: 230,
          decoration: BoxDecoration(
            color: t.ground2,
            border: Border(right: BorderSide(color: t.line)),
          ),
          child: FileTree(
              root: _root!, activePath: active?.path, onOpen: _openFile),
        ),
        Expanded(
          child: Column(
            children: [
              _tabBar(t),
              Expanded(
                child: active == null
                    ? const FwEmpty('Open a file from the tree.')
                    : EditorPane(
                        file: active,
                        onSave: () => _save(active),
                        onChanged: () {
                          if (!active.dirty) setState(() => active.dirty = true);
                        },
                      ),
              ),
              if (_status != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s4, vertical: 4),
                  child: Text(_status!,
                      style: fwMono(t, size: 10.5, color: t.inkFaint)),
                ),
              AgentPanel(
                client: widget.client,
                alive: widget.alive,
                workspaceRoot: _root!,
                activeFile: active?.path,
                selection: _selectionOf(active),
                onRunFinished: _reloadCleanFiles,
              ),
            ],
          ),
        ),
      ],
    );
  }

  String? _selectionOf(OpenFile? f) {
    if (f == null) return null;
    final sel = f.controller.selection;
    if (!sel.isValid || sel.isCollapsed) return null;
    return sel.textInside(f.controller.text);
  }

  Widget _tabBar(FwTokens t) {
    return Container(
      height: 34,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(bottom: BorderSide(color: t.line)),
      ),
      child: Row(
        children: [
          Expanded(
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (var i = 0; i < _open.length; i++) _tab(t, i),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(right: FwLayout.s2),
            child: MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: () => setState(() {
                  for (final f in _open) {
                    f.controller.dispose();
                  }
                  _open.clear();
                  _active = -1;
                  _root = null;
                }),
                child: Text('close workspace',
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tab(FwTokens t, int i) {
    final f = _open[i];
    final active = i == _active;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => setState(() => _active = i),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: FwLayout.s3),
          decoration: BoxDecoration(
            color: active ? t.ground : Colors.transparent,
            border: Border(
              right: BorderSide(color: t.hairline),
              top: BorderSide(
                  color: active ? t.drift : Colors.transparent, width: 2),
            ),
          ),
          child: Row(
            children: [
              if (f.dirty) ...[
                const VerdictDot('drift', size: 6),
                const SizedBox(width: 5),
              ],
              Text(f.name,
                  style: fwMono(t,
                      size: 11.5,
                      color: active ? t.ink : t.inkMuted,
                      weight: active ? FontWeight.w600 : FontWeight.w400)),
              const SizedBox(width: 6),
              GestureDetector(
                onTap: () => _closeFile(i),
                child: Icon(Icons.close, size: 11, color: t.inkFaint),
              ),
            ],
          ),
        ),
      ),
    );
  }

}
