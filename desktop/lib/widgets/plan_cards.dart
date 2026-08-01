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

  /// POST /api/forge/recheck against the server-held seal; when provided
  /// and the plan carries its prp_id, the card offers the drift check.
  final Future<Map<String, dynamic>> Function(String prpId)? recheck;
  const ForgedPlanCard(
      {super.key, required this.plan, this.profile, this.recheck});

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
        if (recheck != null && plan.prpId.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          RecheckRow(prpId: plan.prpId, recheck: recheck!),
        ],
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

/// The Y-chain drift check, in place: one tap re-hashes the sealed arms
/// against the server-held seal and says moved or held per arm.
class RecheckRow extends StatefulWidget {
  final String prpId;
  final Future<Map<String, dynamic>> Function(String prpId) recheck;
  const RecheckRow({super.key, required this.prpId, required this.recheck});

  @override
  State<RecheckRow> createState() => _RecheckRowState();
}

class _RecheckRowState extends State<RecheckRow> {
  bool _busy = false;
  Map<String, dynamic>? _out;

  Future<void> _run() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final r = await widget.recheck(widget.prpId);
      if (mounted) setState(() => _out = r);
    } catch (e) {
      if (mounted) setState(() => _out = {'error': '$e'});
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final out = _out;
    final arms = out?['arms'] is Map<String, dynamic>
        ? out!['arms'] as Map<String, dynamic>
        : const <String, dynamic>{};
    return Row(children: [
      OutlinedButton(
        onPressed: _busy ? null : _run,
        child: Text(_busy ? 'Rechecking…' : 'Re-check seal'),
      ),
      const SizedBox(width: FwLayout.s3),
      if (out?['error'] != null)
        Expanded(child: HonestNull('${out!['error']}'))
      else ...[
        for (final e in arms.entries) ...[
          VerdictPill(
              '${e.key} ${(e.value as Map)['moved'] == true ? 'moved' : 'held'}',
              status:
                  (e.value as Map)['moved'] == true ? 'drift' : 'verified'),
          const SizedBox(width: FwLayout.s2),
        ],
        if (out != null && arms.isEmpty)
          Text('no arms on the seal to check',
              style: fwMono(t, size: 11, color: t.inkFaint)),
      ],
    ]);
  }
}
