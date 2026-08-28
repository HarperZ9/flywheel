// lessons_view.dart -- the organizational learning loop, rendered as the
// feedback edge it is: surfaced patterns for human admission, the chain
// verdict that says the memory is intact, and the improvement candidates
// that compose into the same admission pipeline as the efficiency loop.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/lesson_details.dart';

class LessonsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const LessonsView({super.key, required this.client, required this.alive});

  @override
  State<LessonsView> createState() => _LessonsViewState();
}

class _LessonsViewState extends State<LessonsView> {
  Map<String, dynamic>? _doc;
  Map<String, dynamic>? _patterns;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(LessonsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive || _loading) return;
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.client.lessons(),
        widget.client.lessonsPatterns(),
      ]);
      if (mounted) {
        setState(() {
          _doc = results[0];
          _patterns = results[1];
        });
      }
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
          'The engine is offline. Lessons appear when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('Lessons unavailable: $_error');
    if (_doc == null) {
      return const Center(
          child: SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2)));
    }
    return ViewScroll(
      children: [
        const SectionHeader('Lessons',
            kicker: 'the organizational learning loop'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The layer above audit. Lessons are claims derived from witnessed '
          'divergences (a drift, a rollback, a graded failure), sealed by hash '
          'to their evidence. Recurring patterns surface here as improvement '
          'candidates for human admission, never autonomous change.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _StatRow(doc: _doc!),
        const SizedBox(height: FwLayout.s4),
        _VerifyVerdict(doc: _doc!),
        const SizedBox(height: FwLayout.s4),
        _ImprovementCandidates(doc: _doc!),
        const SizedBox(height: FwLayout.s4),
        if (_patterns != null)
          LessonPatternsDetail(
            patterns: _patterns!,
            client: widget.client,
            onChanged: _load,
          ),
      ],
    );
  }
}

class _StatRow extends StatelessWidget {
  final Map<String, dynamic> doc;
  const _StatRow({required this.doc});

  @override
  Widget build(BuildContext context) {
    final feed = (doc['improvement_feed'] ?? {}) as Map<String, dynamic>;
    final profile = (feed['profile'] ?? {}) as Map<String, dynamic>;
    final n = doc['n'] ?? 0;
    final nPatterns = profile['n_patterns'] ?? 0;
    final nOrgans = profile['n_source_organs'] ?? 0;
    return AdaptiveTiles(children: [
      StatTile(label: 'lessons', value: '$n'),
      StatTile(label: 'patterns', value: '$nPatterns',
          status: nPatterns > 0 ? 'drift' : 'verified'),
      StatTile(label: 'source organs', value: '$nOrgans'),
    ]);
  }
}

class _VerifyVerdict extends StatelessWidget {
  final Map<String, dynamic> doc;
  const _VerifyVerdict({required this.doc});

  @override
  Widget build(BuildContext context) {
    final verify = (doc['verify'] ?? {}) as Map<String, dynamic>;
    final verdict = verify['verdict'] ?? 'unknown';
    final n = verify['n'] ?? 0;
    final status = verdict == 'MATCH' ? 'verified' : 'drift';
    return HairlineCard(
      child: Row(children: [
        const Kicker('chain verdict'),
        const Spacer(),
        VerdictPill('$verdict', status: status),
        const SizedBox(width: FwLayout.s3),
        Text('$n lessons',
            style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}

class _ImprovementCandidates extends StatelessWidget {
  final Map<String, dynamic> doc;
  const _ImprovementCandidates({required this.doc});

  @override
  Widget build(BuildContext context) {
    final feed = (doc['improvement_feed'] ?? {}) as Map<String, dynamic>;
    final candidates = (feed['improvement_candidates'] ?? []) as List;
    final summary = feed['feed_summary'] ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('improvement candidates . for human admission'),
        const SizedBox(height: FwLayout.s2),
        if (candidates.isEmpty)
          const HonestNull('No recurring patterns yet. The loop surfaces '
              'patterns when lessons converge.')
        else
          for (final c in candidates)
            Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s2),
              child: HairlineCard(
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.feedback_outlined,
                      size: 16,
                      color: Theme.of(context).colorScheme.onSurfaceVariant),
                  const SizedBox(width: FwLayout.s3),
                  Expanded(
                    child: Text('$c',
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
                ]),
              ),
            ),
        if ('$summary'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('$summary',
              style: fwMono(context.fw, size: 11)
                  .copyWith(color: context.fw.inkFaint)),
        ],
      ],
    );
  }
}

