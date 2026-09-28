// start_task_prelude.dart — the consumer-friendly empty Chat entry.
//
// It keeps the first action as a plain task, then shows the real selected
// model route, access state, and an honest cost null. Workspace work is an
// explicit handoff into the existing Agent mode; this widget never launches a
// local URI or invents a second task runner.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'start_task_route_card.dart';

export 'start_task_handoff.dart';

class StartTaskPrelude extends StatefulWidget {
  final List<EndpointRow> endpoints;
  final String? endpoint;
  final String? chosenModel;
  final bool streaming;
  final String initialText;
  final ValueChanged<String> onDraftChanged;
  final SubmitPrompt onSend;
  final ValueChanged<String> onEndpoint;
  final ValueChanged<String> onModel;
  final Future<Map<String, dynamic>> Function() loadModels;
  final VoidCallback? onOpenModels;
  final ValueChanged<String>? onUseWorkspaceGoal;

  const StartTaskPrelude({
    super.key,
    required this.endpoints,
    required this.endpoint,
    required this.chosenModel,
    required this.streaming,
    required this.initialText,
    required this.onDraftChanged,
    required this.onSend,
    required this.onEndpoint,
    required this.onModel,
    required this.loadModels,
    this.onOpenModels,
    this.onUseWorkspaceGoal,
  });

  @override
  State<StartTaskPrelude> createState() => _StartTaskPreludeState();
}

class _StartTaskPreludeState extends State<StartTaskPrelude> {
  late final TextEditingController _controller;
  bool _workspaceOpen = false;
  bool _submitting = false;
  String _lastInitial = '';

  @override
  void initState() {
    super.initState();
    _lastInitial = widget.initialText;
    _controller = TextEditingController(text: widget.initialText);
  }

  @override
  void didUpdateWidget(StartTaskPrelude oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialText != _lastInitial &&
        widget.initialText != _controller.text) {
      _lastInitial = widget.initialText;
      _controller.text = widget.initialText;
      _controller.selection =
          TextSelection.collapsed(offset: widget.initialText.length);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  EndpointRow? get _selectedEndpoint {
    final name = widget.endpoint;
    if (name == null) return null;
    for (final row in widget.endpoints) {
      if (row.name == name) return row;
    }
    return null;
  }

  bool get _routeReady => _selectedEndpoint?.usable ?? false;
  bool get _canSubmit =>
      !_submitting && !widget.streaming && _controller.text.trim().isNotEmpty;

  Future<void> _activatePrimary() async {
    if (!_routeReady) {
      widget.onOpenModels?.call();
      return;
    }
    if (!_canSubmit) return;
    setState(() => _submitting = true);
    final submittedText = _controller.text;
    final result = await widget.onSend(submittedText);
    if (!mounted) return;
    if (result == PromptDisposition.accepted &&
        _controller.text == submittedText) {
      _controller.clear();
      widget.onDraftChanged('');
    }
    setState(() => _submitting = false);
  }

  void _useWorkspace() {
    final goal = _controller.text.trim();
    if (goal.isEmpty) return;
    widget.onUseWorkspaceGoal?.call(goal);
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent ||
        event.logicalKey != LogicalKeyboardKey.enter) {
      return KeyEventResult.ignored;
    }
    if (_controller.value.composing case final range
        when range.isValid && !range.isCollapsed) {
      return KeyEventResult.ignored;
    }
    if (HardwareKeyboard.instance.isShiftPressed) {
      _insertNewline();
      return KeyEventResult.handled;
    }
    unawaited(_activatePrimary());
    return KeyEventResult.handled;
  }

  void _insertNewline() {
    final value = _controller.value;
    final text = value.text;
    final selection = value.selection;
    final start = _clampOffset(
        selection.isValid ? selection.start : text.length, text.length);
    final end =
        _clampOffset(selection.isValid ? selection.end : start, text.length);
    final lo = start < end ? start : end;
    final hi = start < end ? end : start;
    final next = text.replaceRange(lo, hi, '\n');
    _controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: lo + 1),
    );
    widget.onDraftChanged(next);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return LayoutBuilder(builder: (context, box) {
      final compact = box.maxHeight < 560 || box.maxWidth < 560;
      return SingleChildScrollView(
        padding: EdgeInsets.all(compact ? FwLayout.s3 : FwLayout.s4),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: HairlineCard(
              padding: EdgeInsets.all(compact ? FwLayout.s4 : FwLayout.s5),
              child: _content(context, t),
            ),
          ),
        ),
      );
    });
  }

  Widget _content(BuildContext context, FwTokens t) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Kicker('start a task', hot: true),
          const SizedBox(height: FwLayout.s2),
          Text('What do you want Flywheel to do?',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: FwLayout.s2),
          Text(
            'Describe the work in plain language. Flywheel will use the '
            'selected route and keep receipts close to the conversation.',
            style: TextStyle(fontSize: 13, height: 1.45, color: t.inkMuted),
          ),
          const SizedBox(height: FwLayout.s3),
          Focus(onKeyEvent: _onKey, child: _taskField(t)),
          const SizedBox(height: FwLayout.s3),
          StartTaskRouteCard(
            endpoints: widget.endpoints,
            endpoint: widget.endpoint,
            chosenModel: widget.chosenModel,
            enabled: !widget.streaming && !_submitting,
            onEndpoint: widget.onEndpoint,
            onModel: widget.onModel,
            loadModels: widget.loadModels,
          ),
          const SizedBox(height: FwLayout.s3),
          _primaryRow(t),
          const SizedBox(height: FwLayout.s2),
          _workspaceDisclosure(t),
        ],
      );

  Widget _primaryRow(FwTokens t) => Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Tooltip(
            message: 'Send  (Enter)',
            child: FilledButton(
              key: const Key('start-task-primary'),
              onPressed: (_routeReady ? _canSubmit : true)
                  ? () => unawaited(_activatePrimary())
                  : null,
              style: FilledButton.styleFrom(minimumSize: const Size(44, 44)),
              child: Text(_primaryLabel),
            ),
          ),
          Text(
            'Shift+Enter adds a line. Research tools, Studio, and receipts '
            'stay reachable after you start.',
            style: fwMono(t, size: 11.5, color: t.inkFaint),
          ),
        ],
      );

  String get _primaryLabel {
    if (!_routeReady) return 'Choose a model';
    if (_submitting || widget.streaming) return 'Waiting…';
    return 'Review and send';
  }

  Widget _taskField(FwTokens t) => TextField(
        key: const Key('start-task-input'),
        controller: _controller,
        minLines: 2,
        maxLines: 6,
        style: TextStyle(fontSize: 14, height: 1.45, color: t.ink),
        decoration: const InputDecoration(
          hintText:
              'Examples: summarize this folder, compare two drafts, find the receipt for a claim…',
        ),
        textInputAction: TextInputAction.newline,
        onChanged: (value) {
          widget.onDraftChanged(value);
          setState(() {});
        },
      );

  Widget _workspaceDisclosure(FwTokens t) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextButton.icon(
            key: const Key('start-task-workspace-toggle'),
            onPressed: widget.onUseWorkspaceGoal == null
                ? null
                : () => setState(() => _workspaceOpen = !_workspaceOpen),
            style: TextButton.styleFrom(minimumSize: const Size(44, 44)),
            icon: Icon(_workspaceOpen
                ? Icons.expand_less_rounded
                : Icons.folder_open_outlined),
            label: const Text('Use a workspace'),
          ),
          if (_workspaceOpen) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(
              'Workspace tasks use Agent mode with an explicit folder. Reads '
              'are free; writes and shell commands stay behind per-run grants.',
            ),
            const SizedBox(height: FwLayout.s2),
            OutlinedButton(
              key: const Key('start-task-use-workspace'),
              onPressed: _controller.text.trim().isEmpty ? null : _useWorkspace,
              style: OutlinedButton.styleFrom(minimumSize: const Size(44, 44)),
              child: const Text('Use workspace for this task'),
            ),
          ],
        ],
      );
}

int _clampOffset(int offset, int length) {
  if (offset < 0) return 0;
  if (offset > length) return length;
  return offset;
}
