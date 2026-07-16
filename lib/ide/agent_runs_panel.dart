// agent_runs_panel.dart — past agent runs and their stored traces. A stored
// run replays through the SAME timeline the live stream uses: one grammar
// for the agent's process, live or at rest. The pill is the content-address
// re-check (intact/TAMPERED), never a claim about the work's quality.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/agent_timeline.dart';
import '../widgets/fw.dart';

class AgentRunsList extends StatelessWidget {
  final List<Map<String, dynamic>> runs;
  final void Function(Map<String, dynamic> run)? onOpen;
  const AgentRunsList({super.key, required this.runs, this.onOpen});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (runs.isEmpty) {
      return const HonestNull(
          'No stored runs yet. Every agent run lands here, content-addressed, '
          'the moment it finishes — including runs you detached from.');
    }
    return Column(children: [for (final r in runs) _row(t, r)]);
  }

  Widget _row(FwTokens t, Map<String, dynamic> r) {
    final intact = r['intact'] == true;
    return InkWell(
      onTap: onOpen == null ? null : () => onOpen!(r),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
        decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(
          children: [
            VerdictPill(intact ? 'intact' : 'TAMPERED',
                status: intact ? 'verified' : 'drift'),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: Text('${r['goal_excerpt'] ?? ''}',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12, color: t.inkSoft)),
            ),
            if (r['steps'] != null) ...[
              const SizedBox(width: FwLayout.s3),
              Text('${r['steps']} steps',
                  style: fwMono(t, size: 10.5, color: t.inkMuted)),
            ],
            const SizedBox(width: FwLayout.s3),
            Text('${r['endpoint'] ?? ''}',
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ],
        ),
      ),
    );
  }
}

/// One stored run: the TAMPERED banner first when the content-address fails,
/// then the replayed trace, then the run's own done data and receipt id.
class StoredAgentRun extends StatelessWidget {
  final Map<String, dynamic> doc;
  const StoredAgentRun({super.key, required this.doc});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final events = ((doc['events'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (doc['intact'] != true) ...[
          const HonestNull(
              'TAMPERED: this stored run no longer matches its '
              'content-address. What follows cannot be trusted as the '
              'original trace.'),
          const SizedBox(height: FwLayout.s2),
        ],
        if (events.isEmpty)
          const HonestNull(
              'No step events were stored with this run; only its outcome '
              'survives below.')
        else
          AgentTimeline(events: events),
        const SizedBox(height: FwLayout.s2),
        // the outcome is the doc itself, rendered as the done event so a
        // stored run reads exactly like the end of a live one
        AgentTimeline(events: [
          {...doc, 'type': 'done'}
        ]),
        Row(
          children: [
            HashText('run', '${doc['run_id'] ?? ''}', keep: 16),
            const Spacer(),
            Text('${doc['started'] ?? ''}',
                style: fwMono(t, size: 10, color: t.inkFaint)),
          ],
        ),
      ],
    );
  }
}
