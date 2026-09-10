// assistant_panel.dart -- talk to the assistant: one command, one action.
//
// A work request runs through the accountable agent sink and keeps its operation
// receipts; music, navigation, and timers are quick device actions. The panel
// shows a small trail of what it carried out, honest about each result: a started
// operation id, or the deep link a device action opens. Tasks already retained by
// the gateway's Relay store are recovered and shown alongside, so a run started on
// another device is visible here too. On the phone this is where speech in and out
// plug in; typed input is the always-available fallback.

import 'dart:async';

import 'package:flutter/material.dart';

import '../assistant/assistant_executor.dart';
import '../assistant/assistant_identity.dart';
import '../assistant/assistant_intent.dart';
import '../assistant/assistant_task_controller.dart';
import '../assistant/voice.dart';
import '../controllers/rowan_operation_controller.dart';
import '../theme/flywheel_theme.dart';
import 'assistant_task_list.dart';
import 'fw.dart';
import 'rowan_operation_card.dart';

Future<void> showAssistantPanel(
  BuildContext context, {
  required AssistantExecutor executor,
  RowanOperationController? rowan,
  VoiceInput voiceInput = const SilentVoice(),
  VoiceOutput voiceOutput = const SilentVoice(),
}) {
  return showDialog(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: ctx.fw.ground,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 560),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: AssistantPanel(
            executor: executor,
            rowan: rowan,
            voiceInput: voiceInput,
            voiceOutput: voiceOutput,
          ),
        ),
      ),
    ),
  );
}

class AssistantPanel extends StatefulWidget {
  final AssistantExecutor executor;
  final RowanOperationController? rowan;
  final VoiceInput voiceInput;
  final VoiceOutput voiceOutput;
  const AssistantPanel({
    super.key,
    required this.executor,
    this.rowan,
    this.voiceInput = const SilentVoice(),
    this.voiceOutput = const SilentVoice(),
  });

  @override
  State<AssistantPanel> createState() => _AssistantPanelState();
}

class _AssistantPanelState extends State<AssistantPanel> {
  final _input = TextEditingController();
  final _root = TextEditingController();
  final _tokens = TextEditingController();
  final _timeout = TextEditingController();
  bool _busy = false;
  Timer? _poll;
  AssistantTaskController? get _tasks => widget.executor.tasks;

  @override
  void initState() {
    super.initState();
    final rowan = widget.rowan;
    if (rowan != null) {
      _root.text = rowan.workspaceRoot ?? '';
      _tokens.text = '${rowan.maxTokens}';
      _timeout.text = '${rowan.timeoutSeconds}';
      rowan.addListener(_rowanChanged);
      unawaited(rowan.loadEndpoints());
      unawaited(rowan.recoverFromSession().catchError((_) => false));
    }
    _connectTasks();
  }

  void _connectTasks() {
    _tasks?.addListener(_tasksChanged);
    _tasks?.recover();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      _tasks?.refreshTracked();
    });
  }

  void _tasksChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(AssistantPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.executor != widget.executor) {
      oldWidget.executor.tasks?.removeListener(_tasksChanged);
      _poll?.cancel();
      _connectTasks();
    }
  }

  @override
  void dispose() {
    widget.rowan?.removeListener(_rowanChanged);
    _poll?.cancel();
    _tasks?.removeListener(_tasksChanged);
    _input.dispose();
    _root.dispose();
    _tokens.dispose();
    _timeout.dispose();
    super.dispose();
  }

  void _rowanChanged() {
    final rowan = widget.rowan;
    if (!mounted || rowan == null) return;
    if (_root.text != (rowan.workspaceRoot ?? '')) {
      _root.text = rowan.workspaceRoot ?? '';
    }
    if (_tokens.text != '${rowan.maxTokens}') {
      _tokens.text = '${rowan.maxTokens}';
    }
    if (_timeout.text != '${rowan.timeoutSeconds}') {
      _timeout.text = '${rowan.timeoutSeconds}';
    }
    setState(() {});
  }

  Future<void> _run(String text) async {
    if (text.isEmpty || _busy) return;
    setState(() => _busy = true);
    final record = await widget.executor.handle(text);
    if (!mounted) return;
    _input.clear();
    setState(() => _busy = false);
    await widget.voiceOutput.speak(
      record.reply,
    ); // no-op unless a speaker is wired
  }

  void _send() => _run(_input.text.trim());

  Future<void> _listen() async {
    if (_busy) return;
    final heard = await widget.voiceInput.listen();
    if (mounted && heard != null && heard.trim().isNotEmpty) {
      await _run(heard.trim());
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final log = widget.executor.log.reversed.toList(); // newest first
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker(AssistantIdentity.name, hot: true),
        const SizedBox(height: FwLayout.s2),
        const Text(
          'Ask for work, or say what you need.',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: FwLayout.s2),
        Text(
          'A work request becomes a reviewed supervised operation. Music, '
          'navigation, and timers are quick device actions.',
          style: TextStyle(fontSize: 11.5, color: t.inkFaint),
        ),
        if (widget.rowan != null) ...[
          const SizedBox(height: FwLayout.s3),
          RowanOperationCard(
            rowan: widget.rowan!,
            root: _root,
            tokens: _tokens,
            timeout: _timeout,
            onRun: _send,
          ),
        ],
        const SizedBox(height: FwLayout.s4),
        Flexible(
          child: log.isEmpty && _tasks == null
              ? const HonestNull(
                  'Nothing yet. Try "navigate to the airport" or "fix the failing test".',
                )
              : ListView(
                  shrinkWrap: true,
                  children: [
                    for (final record in log)
                      Padding(
                        padding: const EdgeInsets.only(bottom: FwLayout.s2),
                        child: _record(t, record),
                      ),
                    if (_tasks != null) AssistantTaskList(controller: _tasks!),
                  ],
                ),
        ),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            if (widget.voiceInput.available) ...[
              IconButton(
                key: const Key('assistant-mic'),
                icon: const Icon(Icons.mic, size: 20),
                tooltip: 'Speak a command',
                onPressed: _busy ? null : _listen,
              ),
              const SizedBox(width: FwLayout.s1),
            ],
            Expanded(
              child: TextField(
                key: const Key('assistant-input'),
                controller: _input,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'Type a command...',
                ),
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: FwLayout.s2),
            FilledButton(
              onPressed: _busy ? null : _send,
              child: const Text('Send'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _record(FwTokens t, AssistantRecord r) {
    final agentDetail = r.runId != null
        ? (_operationish(r.runId!) ? 'operation ${r.runId}' : 'run ${r.runId}')
        : 'could not start the operation';
    final detail = r.channel == AssistantChannel.agent
        ? agentDetail
        : (r.deepLink != null ? 'opens ${r.deepLink}' : '');
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(r.command, style: fwMono(t, size: 11)),
          const SizedBox(height: 2),
          Text(r.reply, style: TextStyle(fontSize: 12, color: t.ink)),
          if (detail.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              detail,
              style: fwMono(t, size: 10, color: r.ok ? t.inkFaint : t.drift),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }

  bool _operationish(String value) =>
      value.startsWith('op_') ||
      value.startsWith('request ') ||
      value == 'operation pending';
}
