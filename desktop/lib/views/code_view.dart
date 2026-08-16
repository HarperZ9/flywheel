import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../ide/agent_panel.dart';
import '../ide/code_buffer_session.dart';
import '../ide/diff.dart';
import '../ide/diff_view.dart';
import '../ide/editor_pane.dart';
import '../ide/file_tree.dart';
import '../ide/lint_index_sheet.dart';
import '../ide/lsp_config.dart';
import '../ide/open_panel.dart';
import '../ide/tab_bar.dart';
import '../ide/unsaved_work_guard.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/split_pane.dart';

class CodeView extends StatefulWidget {
  const CodeView({
    super.key,
    required this.client,
    required this.alive,
    required this.settings,
    required this.session,
    required this.guard,
  });

  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  final CodeBufferSession session;
  final UnsavedWorkGuard guard;

  @override
  State<CodeView> createState() => _CodeViewState();
}

class _CodeViewState extends State<CodeView> {
  final _agentGoal = TextEditingController();

  @override
  void dispose() {
    _agentGoal.dispose();
    super.dispose();
  }

  void _openWorkspace(String path) {
    try {
      widget.session.openWorkspace(path.trim());
      widget.settings.rememberWorkspace(widget.session.workspaceRoot!);
      widget.session.recover();
    } catch (_) {
      widget.session.report('workspace unavailable');
    }
  }

  void _openFile(String path) {
    try {
      widget.session.openFile(path);
    } catch (_) {
      widget.session.report('file unavailable');
    }
  }

  void _save(OpenFile file) {
    if (!widget.session.save(file.path)) return;
    resolveDiagnostics(widget.client, file, widget.session.workspaceRoot!)
        .then((value) {
      if (value != null) widget.session.report('saved ${file.name} · $value');
    });
  }

  Future<void> _goToDefinition(OpenFile file) async {
    widget.session.report('definition…');
    final result = await resolveDefinition(
        widget.client, file, widget.session.workspaceRoot!);
    if (result.target == null) {
      widget.session.report(result.message);
      return;
    }
    _openFile(result.target!.path);
    final opened = _active;
    if (opened == null) return;
    opened.controller.selection = TextSelection.collapsed(
        offset: offsetOf(opened.controller.text, result.target!.line,
            result.target!.character));
    widget.session.report('definition: ${opened.name}');
  }

  Future<void> _findReferences(OpenFile file) async {
    widget.session.report('references…');
    final result = await resolveReferences(
        widget.client, file, widget.session.workspaceRoot!);
    widget.session.report(result.message);
    if (result.targets.isEmpty || !mounted) return;
    showReferencesSheet(context, result.targets, (target) {
      _openFile(target.path);
      final opened = _active;
      if (opened == null) return;
      opened.controller.selection = TextSelection.collapsed(
          offset:
              offsetOf(opened.controller.text, target.line, target.character));
    });
  }

  void _showDiffs() {
    showDiffSheet(context, widget.session.diffs, (diff, anchor, note) {
      final current = _agentGoal.text.trimRight();
      _agentGoal.text = '${current.isEmpty ? '' : '$current\n'}'
          'CHANGE REQUEST [${diff.path} @ $anchor]: $note';
      Navigator.of(context).pop();
      widget.session.report('change request anchored to ${diff.path}');
    });
  }

  void _openAt(String path, int line) {
    _openFile(path);
    final opened = _active;
    if (opened == null) return;
    opened.controller.selection = TextSelection.collapsed(
        offset: offsetOf(opened.controller.text, line - 1, 0));
  }

  OpenFile? get _active {
    final index = widget.session.activeIndex;
    final open = widget.session.openFiles;
    return index >= 0 && index < open.length ? open[index] : null;
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.session,
        builder: (context, _) => _content(context),
      );

  Widget _content(BuildContext context) {
    final root = widget.session.workspaceRoot;
    if (root == null) {
      return OpenWorkspacePanel(
          settings: widget.settings,
          onOpen: _openWorkspace,
          status: widget.session.status);
    }
    final active = _active;
    return SplitPane(
      axis: Axis.horizontal,
      initialFraction: 0.2,
      minFraction: 0.1,
      maxFraction: 0.45,
      first: Container(
        color: context.fw.ground2,
        child:
            FileTree(root: root, activePath: active?.path, onOpen: _openFile),
      ),
      second: _workArea(root, active),
    );
  }

  Widget _workArea(String root, OpenFile? active) => SplitPane(
        axis: Axis.vertical,
        initialFraction: 0.66,
        minFraction: 0.3,
        maxFraction: 0.88,
        first: Column(children: [
          EditorTabBar(
            open: widget.session.openFiles,
            active: widget.session.activeIndex,
            onSelect: widget.session.selectIndex,
            onClose: (index) => unawaited(widget.guard
                .requestFileClose(widget.session.openFiles[index].path)),
            onCloseWorkspace: () =>
                unawaited(widget.guard.requestWorkspaceClose()),
          ),
          if (_recoveryNotice case final String notice)
            Padding(
              padding: const EdgeInsets.all(FwLayout.s2),
              child: HonestNull(notice),
            ),
          if (widget.session.conflicts.isNotEmpty)
            _conflict(widget.session.conflicts.last)
          else
            Expanded(
              child: active == null
                  ? const FwEmpty('Open a file from the tree.')
                  : EditorPane(
                      file: active,
                      onSave: () => _save(active),
                      onDefinition: () => _goToDefinition(active),
                      onReferences: () => _findReferences(active),
                      onChanged: () => widget.session.snapshot(active.path),
                    ),
            ),
          EditorQualityBar(
            status: widget.session.status,
            diffCount: widget.session.diffs.length,
            onLint: () => showLintIndexSheet(
                context, widget.client, root, _openAt,
                index: false),
            onIndex: () => showLintIndexSheet(
                context, widget.client, root, _openAt,
                index: true),
            onShowDiffs: _showDiffs,
          ),
        ]),
        second: SingleChildScrollView(
          child: AgentPanel(
            client: widget.client,
            alive: widget.alive,
            workspaceRoot: root,
            currentAttachment: () => editorAttachmentOf(_active),
            goalController: _agentGoal,
            onRunStarted: widget.session.snapshotOpenFiles,
            onRunFinished: widget.session.reloadCleanFiles,
          ),
        ),
      );

  Widget _conflict(CodeRecoveryConflict conflict) => Expanded(
        child: Column(children: [
          HonestNull(conflict.kind == CodeRecoveryKind.fileMissing
              ? '${conflict.path}: file missing; draft retained'
              : '${conflict.path}: disk changed; draft retained'),
          Expanded(
            child: DiffViewPanel(diffs: [
              diffFiles(conflict.path, conflict.diskText ?? '',
                  conflict.stored.draft.text)
            ]),
          ),
        ]),
      );

  String? get _recoveryNotice {
    final values = widget.session.recoveryOutcomes;
    if (values.isEmpty) return null;
    final value = values.last;
    return switch (value.kind) {
      CodeRecoveryKind.restored => 'Draft restored: ${value.path}',
      CodeRecoveryKind.alreadySaved =>
        'Completed save recovered: ${value.path}',
      _ => null,
    };
  }
}
