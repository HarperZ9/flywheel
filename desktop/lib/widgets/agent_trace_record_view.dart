import 'package:flutter/material.dart';
import '../models/agent_trace_record.dart';
import '../theme/flywheel_theme.dart';

/// Displays the original canonical material without re-encoding payload numbers.
/// Text windows bound layout cost; all original characters remain accessible.
class AgentTraceRecordView extends StatefulWidget {
  final TraceRecord record;
  const AgentTraceRecordView({super.key, required this.record});
  @override
  State<AgentTraceRecordView> createState() => _AgentTraceRecordViewState();
}

class _AgentTraceRecordViewState extends State<AgentTraceRecordView> {
  static const _window = 16384;
  int _offset = 0;
  final List<int> _previous = [];
  @override
  void didUpdateWidget(covariant AgentTraceRecordView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.record.recordSha256 != widget.record.recordSha256) {
      _offset = 0;
      _previous.clear();
    }
  }

  int get _end {
    final text = widget.record.canonicalText;
    var end = (_offset + _window).clamp(0, text.length);
    // Do not split an original Unicode surrogate pair between text windows.
    if (end < text.length &&
        end > _offset &&
        text.codeUnitAt(end - 1) >= 0xd800 &&
        text.codeUnitAt(end - 1) <= 0xdbff) {
      end--;
    }
    return end;
  }

  @override
  Widget build(BuildContext context) {
    final record = widget.record, t = context.fw, end = _end;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Original ${record.kind} record · sequence ${record.sequence}',
          style: Theme.of(context).textTheme.bodyMedium),
      SelectableText(
          'Owner ${record.ownerRef}\nSHA-256 ${record.recordSha256}\n'
          'Prior ${record.priorSha256}',
          style: fwMono(t, size: 11)),
      Text(
          'Ownership enforced by the authenticated gateway; the owner binding matches the trace reference.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: t.inkMuted)),
      Text(
          'Original canonical record material (${record.byteCount} UTF-8 bytes). '
          'The record digest is shown separately.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: t.inkMuted)),
      if (record.canonicalText.length > _window)
        Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text(
              'Text units ${_offset + 1}–$end of ${record.canonicalText.length}'),
          TextButton(
              onPressed: _previous.isEmpty
                  ? null
                  : () => setState(() {
                        _offset = _previous.removeLast();
                      }),
              child: const Text('Previous text')),
          TextButton(
              onPressed: end == record.canonicalText.length
                  ? null
                  : () => setState(() {
                        _previous.add(_offset);
                        _offset = end;
                      }),
              child: const Text('Next text')),
        ]),
      ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 360),
          child: SingleChildScrollView(
              child: SelectableText(
                  record.canonicalText.substring(_offset, end),
                  style: fwMono(t, size: 12)))),
    ]);
  }
}
