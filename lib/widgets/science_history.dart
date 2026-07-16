// science_history.dart — the stored science runs, each re-verified at read
// time. The pill only ever reflects the chain re-check (intact/TAMPERED);
// claim verdicts render as text so color keeps meaning a verdict the engine
// actually recomputed. Every row opens its full stored run.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ScienceHistoryList extends StatelessWidget {
  final List<Map<String, dynamic>> runs;
  final void Function(Map<String, dynamic> run)? onOpen;
  const ScienceHistoryList({super.key, required this.runs, this.onOpen});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s4, vertical: FwLayout.s2),
      child: Column(children: [for (final r in runs) _row(t, r)]),
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> r) {
    final ok = r['chain_ok'] == true;
    final counts = (r['verdicts'] is Map)
        ? (r['verdicts'] as Map)
            .entries
            .map((e) => '${e.value} ${e.key}')
            .join(' · ')
        : '';
    return InkWell(
      onTap: onOpen == null ? null : () => onOpen!(r),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
        decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(
          children: [
            VerdictPill(ok ? 'intact' : 'TAMPERED',
                status: ok ? 'verified' : 'drift'),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: Text('${r['question'] ?? ''}',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12.5, color: t.inkSoft)),
            ),
            if (counts.isNotEmpty) ...[
              const SizedBox(width: FwLayout.s3),
              Text(counts, style: fwMono(t, size: 10.5, color: t.inkMuted)),
            ],
            const SizedBox(width: FwLayout.s3),
            Text('${r['started'] ?? ''}',
                style: fwMono(t, size: 10, color: t.inkFaint)),
          ],
        ),
      ),
    );
  }
}
