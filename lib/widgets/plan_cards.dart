// plan_cards.dart — rendering for a forged plan: engine-scored stat tiles,
// per-gate checkability verdicts, the profile's discipline steps, and the
// full PRP as selectable mono provenance. Pure rendering; every number here
// is the engine's.

import 'package:flutter/material.dart';

import '../models/plan_models.dart';
import '../models/workflow_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ForgedPlanCard extends StatelessWidget {
  final ForgedPlan plan;
  final ProfileManifest? profile;
  const ForgedPlanCard({super.key, required this.plan, this.profile});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final p = profile;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Kicker('forged plan · ${plan.taskType} task', hot: true),
        const SizedBox(height: FwLayout.s3),
        AdaptiveTiles(children: [
          StatTile(label: 'confidence', value: '${plan.confidence}/10'),
          StatTile(
              label: 'oracle gates',
              value: '${(plan.externalGateRatio * 100).round()}%'),
          StatTile(label: 'gates', value: '${plan.gates.length}'),
        ]),
        if (!plan.wellPosed) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'The goal did not state a checkable criterion; the forge '
              'proposed one. Confirm it before running the plan.'),
        ],
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Kicker('validation gates'),
              const SizedBox(height: FwLayout.s2),
              for (final g in plan.gates)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    VerdictPill(g.label, status: g.verdict),
                    const SizedBox(width: FwLayout.s3),
                    Expanded(
                        child: Text(g.check,
                            style:
                                TextStyle(fontSize: 12.5, color: t.inkSoft))),
                  ]),
                ),
              if (p != null && p.planning.isNotEmpty) ...[
                const SizedBox(height: FwLayout.s3),
                const Kicker('discipline'),
                const SizedBox(height: FwLayout.s2),
                for (final (i, step) in p.planning.indexed)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(children: [
                      Text('${i + 1}'.padLeft(2, '0'),
                          style: fwMono(t, size: 11, color: t.inkFaint)),
                      const SizedBox(width: FwLayout.s3),
                      Text(step,
                          style: TextStyle(fontSize: 12.5, color: t.inkSoft)),
                    ]),
                  ),
              ],
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          recessed: true,
          child: SelectableText(plan.prompt,
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
        ),
      ],
    );
  }
}
