// academy_view.dart -- the curriculum derived from the live code, rendered
// as the arc it is: foundations before composition, every lesson pinned
// to its source hash, every check runnable in place, completion bound to
// a passed comprehension receipt, absence shown not papered.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/academy_lesson.dart';
import '../widgets/fw.dart';

class AcademyView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const AcademyView({super.key, required this.client, required this.alive});

  @override
  State<AcademyView> createState() => _AcademyViewState();
}

class _AcademyViewState extends State<AcademyView> {
  Map<String, dynamic>? _doc;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(AcademyView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() => _loading = true);
    try {
      final doc = await widget.client.academy();
      if (mounted) setState(() => _doc = doc);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The curriculum appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('Curriculum unavailable: $_error');
    if (_doc == null) {
      return const Center(
          child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2)));
    }
    return ViewScroll(
      children: [
        const SectionHeader('Academy',
            kicker: 'lessons pinned to the live code'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Each lesson\'s teach-text is the live module docstring, pinned by '
          'hash, so documentation rot breaks a lesson visibly. Run the '
          'declared check right here, then bind your completion to a passed '
          'teach-back receipt.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        AcademyArc(
          _doc!,
          onRunCheck: widget.client.runLessonCheck,
          onBind: widget.client.academyComplete,
          onAnimate: widget.client.learnAnimate,
        ),
      ],
    );
  }
}

/// Pure renderer for the curriculum document; testable without a gateway.
/// Callbacks are optional: absent, the cards render read-only.
class AcademyArc extends StatelessWidget {
  final Map<String, dynamic> doc;
  final RunCheck? onRunCheck;
  final BindCompletion? onBind;
  final AnimateLesson? onAnimate;
  const AcademyArc(this.doc,
      {super.key, this.onRunCheck, this.onBind, this.onAnimate});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final lessons = ((doc['lessons'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final present = doc['present_count'];
    final total = doc['total'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          const Kicker('the academy arc'),
          const Spacer(),
          if (present is int && total is int)
            VerdictPill('$present/$total present',
                status: present == total ? 'verified' : 'drift'),
        ]),
        const SizedBox(height: FwLayout.s4),
        for (var i = 0; i < lessons.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s3),
            child: AcademyLessonCard(
              lesson: lessons[i],
              index: i,
              onRunCheck: onRunCheck,
              onBind: onBind,
              onAnimate: onAnimate,
            ),
          ),
        if ('${doc['completion_flow'] ?? ''}'.isNotEmpty)
          HonestNull('${doc['completion_flow']}'),
        if ('${doc['attribution'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('${doc['attribution']}',
              style: fwMono(t, size: 11).copyWith(color: t.inkFaint)),
        ],
      ],
    );
  }
}
