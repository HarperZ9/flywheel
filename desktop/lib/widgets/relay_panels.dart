import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class RelayDetailPane extends StatelessWidget {
  final Map<String, dynamic>? detail;
  final bool loading;
  final VoidCallback onRefresh;
  const RelayDetailPane(
      {super.key, required this.detail, required this.loading,
       required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (loading) {
      return const Padding(
          padding: EdgeInsets.all(FwLayout.s3),
          child: Center(child: CircularProgressIndicator(strokeWidth: 2)));
    }
    final d = detail;
    if (d == null) return const SizedBox.shrink();
    if (d.containsKey('error')) return HonestNull('${d['error']}');
    final toolCalls = d['tool_calls'];
    final toolsText = toolCalls is int ? '$toolCalls tool calls' : '';
    final model = '${d['model'] ?? ''}';
    final elapsed = '${d['elapsed'] ?? ''}';
    final resultDoc = d['result_doc'];
    final output = resultDoc is Map ? '${resultDoc['output'] ?? ''}' : '';
    final receipt = resultDoc is Map ? resultDoc['receipt'] : null;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        if (model.isNotEmpty) ...[
          Kicker('model'),
          const SizedBox(width: FwLayout.s1),
          Text(model, style: fwMono(t, size: 11, color: t.ink)),
        ],
        const Spacer(),
        if (elapsed.isNotEmpty)
          Text(elapsed, style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(width: FwLayout.s2),
        IconButton(
            icon: const Icon(Icons.refresh, size: 16),
            onPressed: onRefresh,
            tooltip: 'Refresh run detail',
            visualDensity: VisualDensity.compact),
      ]),
      if (toolsText.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s1),
        Text(toolsText, style: fwMono(t, size: 11, color: t.inkFaint)),
      ],
      if (output.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s3),
        Kicker('output'),
        const SizedBox(height: FwLayout.s1),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(FwLayout.s3),
          decoration: BoxDecoration(
            color: t.ground2,
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          ),
          child: SelectableText(output,
              style: fwMono(t, size: 11.5, color: t.ink), maxLines: 20),
        ),
      ],
      if (receipt is Map) ...[
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          VerdictDot('verified', size: 6),
          const SizedBox(width: FwLayout.s1),
          Kicker('receipt'),
          const SizedBox(width: FwLayout.s2),
          if (receipt['chain'] != null)
            Expanded(
                child: HashText('chain', '${receipt['chain']}', keep: 16)),
        ]),
      ],
    ]);
  }
}

class RelaySessionCard extends StatelessWidget {
  final Map<String, dynamic> session;
  const RelaySessionCard({super.key, required this.session});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final path = '${session['path'] ?? ''}';
    final entries = session['entries'];
    final entriesText = entries is int ? '$entries entries' : '';
    final root = '${session['root'] ?? ''}';
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (path.isNotEmpty)
          Text(path.split('/').last.split('\\').last,
              style: fwMono(t, size: 12, color: t.ink),
              maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: FwLayout.s1),
        Row(children: [
          if (entriesText.isNotEmpty)
            Text(entriesText, style: fwMono(t, size: 11, color: t.inkFaint)),
          if (root.isNotEmpty) ...[
            const SizedBox(width: FwLayout.s3),
            Expanded(child: HashText('root', root, keep: 16)),
          ],
        ]),
      ]),
    );
  }
}
