// parity_table.dart — the capability matrix rendered honestly: Flywheel
// cells are audited by the engine at read time (they can say ABSENT);
// competitor cells are dated declarations, labeled as such. The gap rows
// are the roadmap, kept visible.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ParityTable extends StatelessWidget {
  final Map<String, dynamic> doc;
  const ParityTable({super.key, required this.doc});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rows = ((doc['rows'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final summary = (doc['summary'] ?? {}) as Map<String, dynamic>;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            VerdictPill('${summary['witnessed'] ?? 0} witnessed',
                status: 'verified'),
            const SizedBox(width: FwLayout.s2),
            VerdictPill(
                '${(summary['uniquely_witnessed'] as List?)?.length ?? 0} unique',
                status: 'verified'),
            const SizedBox(width: FwLayout.s2),
            VerdictPill('${(summary['gaps'] as List?)?.length ?? 0} gaps',
                status: 'drift'),
          ],
        ),
        const SizedBox(height: FwLayout.s2),
        Text('${doc['note'] ?? ''} (declared ${doc['declared_on'] ?? '?'})',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [
              _header(t),
              for (final r in rows) _row(t, r),
            ],
          ),
        ),
      ],
    );
  }

  Widget _header(FwTokens t) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      child: Row(
        children: [
          Expanded(child: Kicker('capability')),
          _cell(t, 'flywheel', header: true),
          _cell(t, 'codex', header: true),
          _cell(t, 'cursor', header: true),
          _cell(t, 'claude', header: true),
        ],
      ),
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> r) {
    final witnessed = r['flywheel'] == 'WITNESSED';
    final comp = (r['competitors'] ?? {}) as Map<String, dynamic>;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration: BoxDecoration(
          border: Border(top: BorderSide(color: t.hairline))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${r['key']}',
                    style: fwMono(t, size: 11.5, weight: FontWeight.w600)),
                Text('${r['desc']}',
                    style: TextStyle(fontSize: 11, color: t.inkFaint)),
              ],
            ),
          ),
          SizedBox(
            width: 78,
            child: VerdictPill(witnessed ? 'witnessed' : 'absent',
                status: witnessed ? 'verified' : 'drift'),
          ),
          _declCell(t, comp['codex']),
          _declCell(t, comp['cursor']),
          _declCell(t, comp['claude-code']),
        ],
      ),
    );
  }

  Widget _cell(FwTokens t, String text, {bool header = false}) => SizedBox(
        width: 78,
        child: Text(text,
            style: header
                ? fwKicker(t, size: 9.5)
                : fwMono(t, size: 11, color: t.inkMuted)),
      );

  Widget _declCell(FwTokens t, dynamic v) {
    final (label, color) = switch (v) {
      true => ('yes', t.inkMuted),
      'partial' => ('partial', t.inkFaint),
      _ => ('no', t.inkFaint),
    };
    return SizedBox(
      width: 78,
      child: Text(label, style: fwMono(t, size: 11, color: color)),
    );
  }
}
