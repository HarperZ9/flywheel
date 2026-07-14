// scaffold_strip.dart — the per-message scaffold made visible.
//
// Every routed answer now carries proof of its perception: sources frozen
// before the answer existed (verified provenance), degradations named with
// reasons (unverifiable, never hidden), and the chained turn receipt. This
// strip renders that receipt under an answer; an empty scaffold renders
// nothing at all.
import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ScaffoldStrip extends StatelessWidget {
  final TurnScaffold? scaffold;
  const ScaffoldStrip(this.scaffold, {super.key});

  @override
  Widget build(BuildContext context) {
    final s = scaffold;
    if (s == null || s.isEmpty) return const SizedBox.shrink();
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: FwLayout.s3),
        const Kicker('turn scaffold'),
        const SizedBox(height: FwLayout.s2),
        for (final f in s.sourcesFrozen)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s1),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 4),
                  child: VerdictDot('verified'),
                ),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                  child: SelectableText(
                    '${f.url}  ${f.sha256.substring(0, f.sha256.length < 16 ? f.sha256.length : 16)}',
                    style: fwMono(t, size: 11).copyWith(color: t.inkSoft),
                  ),
                ),
              ],
            ),
          ),
        for (final d in s.degraded)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s1),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 4),
                  child: VerdictDot('unverifiable'),
                ),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                  child: SelectableText(
                    '${d.url}  ${d.reason}',
                    style: fwMono(t, size: 11).copyWith(color: t.inkMuted),
                  ),
                ),
              ],
            ),
          ),
        if (s.eid.isNotEmpty) HashText('turn receipt', s.eid, keep: 24),
      ],
    );
  }
}
