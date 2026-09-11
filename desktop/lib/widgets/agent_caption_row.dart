import 'package:flutter/material.dart';
import '../models/agent_caption.dart';
import '../theme/flywheel_theme.dart';
import 'agent_trace_record_view.dart';

class AgentCaptionRow extends StatelessWidget {
  final AgentCaption caption;
  final double size;
  final bool showOriginal;
  final VoidCallback onToggleOriginal;
  const AgentCaptionRow(
      {super.key,
      required this.caption,
      required this.size,
      required this.showOriginal,
      required this.onToggleOriginal});
  @override
  Widget build(BuildContext context) {
    final text = caption.text;
    var end = text.length.clamp(0, 600);
    if (end < text.length &&
        end > 0 &&
        text.codeUnitAt(end - 1) >= 0xd800 &&
        text.codeUnitAt(end - 1) <= 0xdbff) {
      end--;
    }
    return Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${caption.label} · sequence ${caption.record.sequence}',
              style: Theme.of(context).textTheme.titleSmall),
          SelectableText(text.substring(0, end),
              style: Theme.of(context)
                  .textTheme
                  .bodyLarge
                  ?.copyWith(fontSize: size, height: 1.5)),
          if (end < text.length)
            const Text(
                'Caption excerpt. Open the original record for the complete retained text.'),
          Text(
              '${caption.source}\nreceived ${caption.receivedAt.toIso8601String()}',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: context.fw.inkMuted)),
          TextButton(
              onPressed: onToggleOriginal,
              child: Text(
                  showOriginal ? 'Hide original record' : 'Original record')),
          if (showOriginal) AgentTraceRecordView(record: caption.record),
        ]));
  }
}
