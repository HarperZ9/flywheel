// training_card.dart — the read-only training supervisor card: state pill,
// progress bar, last event, and an honest note when the log and the live
// process disagree.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'charts.dart';
import 'fw.dart';

class TrainingCard extends StatelessWidget {
  final Map<String, dynamic> training;
  const TrainingCard({super.key, required this.training});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final tr = training;
    final state = '${tr['state'] ?? 'unknown'}';
    final progress =
        (tr['progress'] is num) ? (tr['progress'] as num).toDouble() : 0.0;
    final verdict = switch (state) {
      'completed' => 'verified',
      'running' => 'verified',
      'failed' => 'drift',
      _ => 'unverifiable',
    };
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text('Training · read-only supervisor',
                    style:
                        TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
              ),
              VerdictPill(state, status: verdict),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
          Row(
            children: [
              Expanded(child: MiniBar(progress, width: 200, status: verdict)),
              const SizedBox(width: FwLayout.s3),
              Text(
                  '${tr['checkpoint_step'] ?? '?'}/${tr['target_steps'] ?? '?'} steps',
                  style: fwMono(t, size: 11.5, color: t.inkMuted)),
            ],
          ),
          if ('${tr['last_event'] ?? ''}'.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text('${tr['last_event']}',
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ],
          if (tr['reconciled'] == false) ...[
            const SizedBox(height: FwLayout.s2),
            const HonestNull(
                'The log and the live process disagree; treat this status '
                'as unconfirmed until they reconcile.'),
          ],
        ],
      ),
    );
  }
}
