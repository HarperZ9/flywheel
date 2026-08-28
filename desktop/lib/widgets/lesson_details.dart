import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class LessonPatternsDetail extends StatefulWidget {
  final Map<String, dynamic> patterns;
  final GatewayClient client;
  final VoidCallback onChanged;
  const LessonPatternsDetail({
    super.key,
    required this.patterns,
    required this.client,
    required this.onChanged,
  });

  @override
  State<LessonPatternsDetail> createState() => _LessonPatternsDetailState();
}

class _LessonPatternsDetailState extends State<LessonPatternsDetail> {
  String? _actingOn;
  String? _error;

  Future<void> _admit(String lessonId) async {
    if (_actingOn != null) return;
    setState(() {
      _actingOn = lessonId;
      _error = null;
    });
    try {
      await widget.client.lessonAdmit(lessonId);
      widget.onChanged();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _actingOn = null);
    }
  }

  Future<void> _retire(String lessonId) async {
    if (_actingOn != null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ctx.fw.ground,
        title: const Text('Retire lesson'),
        content: Text('Retire this lesson? It will be marked as no longer '
            'active. The transition is journaled (append-only); the original '
            'lesson stays in the chain as history.\n\n${lessonId.substring(0, 16)}...'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Retire')),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() {
      _actingOn = lessonId;
      _error = null;
    });
    try {
      await widget.client.lessonRetire(lessonId);
      widget.onChanged();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _actingOn = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = (widget.patterns['patterns'] ?? []) as List;
    if (list.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('patterns . converged lessons'),
        const SizedBox(height: FwLayout.s2),
        for (final p in list.whereType<Map<String, dynamic>>())
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s2),
            child: LessonPatternCard(
              pattern: p,
              actingOn: _actingOn,
              onAdmit: _admit,
              onRetire: _retire,
            ),
          ),
        if (_error != null) HonestNull('Failed: $_error'),
      ],
    );
  }
}

class LessonPatternCard extends StatelessWidget {
  final Map<String, dynamic> pattern;
  final String? actingOn;
  final void Function(String) onAdmit;
  final void Function(String) onRetire;
  const LessonPatternCard({
    super.key,
    required this.pattern,
    required this.actingOn,
    required this.onAdmit,
    required this.onRetire,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final lessonIds = (pattern['lesson_ids'] ?? []) as List;
    final firstId = lessonIds.isNotEmpty ? '${lessonIds[0]}' : '';
    final isActing = actingOn == firstId;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('${pattern['source_organ'] ?? 'unknown'}',
                style: fwMono(t, size: 12)
                    .copyWith(fontWeight: FontWeight.w600)),
            const Spacer(),
            VerdictPill('${pattern['repetition_count']}', status: 'drift'),
          ]),
          const SizedBox(height: FwLayout.s2),
          Text('${pattern['improvement_candidate']}',
              style: Theme.of(context).textTheme.bodySmall),
          if ((pattern['confidence'] ?? '').isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text('confidence: ${pattern['confidence']}',
                style: fwMono(t, size: 11).copyWith(color: t.inkFaint)),
          ],
          if (firstId.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              OutlinedButton(
                onPressed: isActing ? null : () => onAdmit(firstId),
                child: Text(isActing ? 'Admitting...' : 'Admit'),
              ),
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                onPressed: isActing ? null : () => onRetire(firstId),
                child: const Text('Retire'),
              ),
            ]),
          ],
        ],
      ),
    );
  }
}
