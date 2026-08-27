// assistant_panel.dart -- talk to the assistant: one command, one action.
//
// A work request runs on the accountable agent (relay via the gateway) and keeps
// its receipts; music, navigation, and timers are quick device actions. The panel
// shows a small trail of what it carried out, honest about each result: a started
// run's id, or the deep link a device action opens. On the phone this is where
// speech in and out plug in; typed input is the always-available fallback.

import 'package:flutter/material.dart';

import '../assistant/assistant_executor.dart';
import '../assistant/assistant_intent.dart';
import '../assistant/voice.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

Future<void> showAssistantPanel(
  BuildContext context, {
  required AssistantExecutor executor,
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
              executor: executor, voiceInput: voiceInput, voiceOutput: voiceOutput),
        ),
      ),
    ),
  );
}

class AssistantPanel extends StatefulWidget {
  final AssistantExecutor executor;
  final VoiceInput voiceInput;
  final VoiceOutput voiceOutput;
  const AssistantPanel({
    super.key,
    required this.executor,
    this.voiceInput = const SilentVoice(),
    this.voiceOutput = const SilentVoice(),
  });

  @override
  State<AssistantPanel> createState() => _AssistantPanelState();
}

class _AssistantPanelState extends State<AssistantPanel> {
  final _input = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _run(String text) async {
    if (text.isEmpty || _busy) return;
    setState(() => _busy = true);
    final record = await widget.executor.handle(text);
    if (!mounted) return;
    _input.clear();
    setState(() => _busy = false);
    await widget.voiceOutput.speak(record.reply); // no-op unless a speaker is wired
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
        const Kicker('assistant', hot: true),
        const SizedBox(height: FwLayout.s2),
        const Text('Ask for work, or say what you need.',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        Text(
            'A work request runs on the accountable agent and keeps its receipts. '
            'Music, navigation, and timers are quick device actions.',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s4),
        Flexible(
          child: log.isEmpty
              ? const HonestNull(
                  'Nothing yet. Try "navigate to the airport" or "fix the failing test".')
              : ListView.separated(
                  shrinkWrap: true,
                  itemCount: log.length,
                  separatorBuilder: (_, __) => const SizedBox(height: FwLayout.s2),
                  itemBuilder: (context, i) => _record(t, log[i]),
                ),
        ),
        const SizedBox(height: FwLayout.s3),
        Row(children: [
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
              decoration:
                  const InputDecoration(isDense: true, hintText: 'Type a command...'),
              onSubmitted: (_) => _send(),
            ),
          ),
          const SizedBox(width: FwLayout.s2),
          FilledButton(onPressed: _busy ? null : _send, child: const Text('Send')),
        ]),
      ],
    );
  }

  Widget _record(FwTokens t, AssistantRecord r) {
    final detail = r.channel == AssistantChannel.agent
        ? (r.runId != null ? 'run ${r.runId}' : 'could not start the run')
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
            Text(detail,
                style: fwMono(t, size: 10, color: r.ok ? t.inkFaint : t.drift),
                overflow: TextOverflow.ellipsis),
          ],
        ],
      ),
    );
  }
}
