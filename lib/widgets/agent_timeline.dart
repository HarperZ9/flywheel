// agent_timeline.dart — the live agent event stream rendered as a witnessed
// timeline: each assistant turn, tool call, and tool result as it happens,
// then the done event with the ledger and integrity verdicts.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class AgentTimeline extends StatelessWidget {
  final List<Map<String, dynamic>> events;
  const AgentTimeline({super.key, required this.events});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [for (final e in events) _event(t, context, e)],
    );
  }

  Widget _event(FwTokens t, BuildContext context, Map<String, dynamic> e) {
    final type = '${e['type'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s2),
      child: switch (type) {
        'assistant' => _assistant(t, e),
        'tool_call' => _toolCall(t, e),
        'tool_result' => _toolResult(t, e),
        'tool_rescue' => _rescue(t, e),
        'done' => _done(t, e),
        'error' => HonestNull('The run failed: ${e['error']}'),
        _ => const SizedBox.shrink(),
      },
    );
  }

  Widget _assistant(FwTokens t, Map<String, dynamic> e) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Kicker('step ${e['step'] ?? '?'}'),
        const SizedBox(height: 2),
        SelectableText('${e['text'] ?? ''}',
            style: fwMono(t, size: 12).copyWith(height: 1.5)),
      ],
    );
  }

  Widget _toolCall(FwTokens t, Map<String, dynamic> e) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('→ ', style: fwMono(t, size: 11.5, color: t.inkFaint)),
        Expanded(
          child: Text('${e['name']} ${e['args'] ?? ''}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
        ),
      ],
    );
  }

  /// A repaired emission is a fact of the run, shown as one: the transform
  /// that fixed it, never a silent in-proxy repair.
  Widget _rescue(FwTokens t, Map<String, dynamic> e) {
    return Text('⟲ rescued: ${e['transform']}',
        style: fwMono(t, size: 11, color: t.inkMuted));
  }

  Widget _toolResult(FwTokens t, Map<String, dynamic> e) {
    final ok = e['ok'] == true;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        VerdictDot(ok ? 'verified' : 'drift', size: 6),
        const SizedBox(width: 6),
        Expanded(
          child: Text('${e['name']}: ${e['output'] ?? ''}',
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: fwMono(t, size: 11, color: t.inkFaint)),
        ),
      ],
    );
  }

  Widget _done(FwTokens t, Map<String, dynamic> e) {
    final integrity = e['integrity'];
    final clean = integrity is Map ? integrity['clean'] == true : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s1,
          children: [
            VerdictPill('${e['steps'] ?? '?'} steps', status: 'unverifiable'),
            if (e['verified'] == true)
              const VerdictPill('ledger verified', status: 'verified'),
            if (clean != null)
              VerdictPill(clean ? 'integrity clean' : 'integrity flagged',
                  status: clean ? 'verified' : 'drift'),
          ],
        ),
        if ('${e['final'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          SelectableText('${e['final']}',
              style: fwMono(t, size: 12.5).copyWith(height: 1.55)),
        ],
      ],
    );
  }
}
