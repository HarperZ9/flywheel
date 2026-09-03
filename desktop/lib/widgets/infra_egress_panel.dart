// infra_egress_panel.dart -- where this machine is actually talking.
//
// The live socket table, each connection classified against the allowlist.
// ALLOWED means a rule named it. UNKNOWN means no rule did, and in
// non-strict mode that is exactly what it says: unclassified, not safe. The
// engine tallies the verdicts; this panel renders the tally and the
// connections that were not allowed, because those are the finding.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// How many unclassified connections are listed one by one. The rest are
/// counted in a line that says so, because a silent truncation reads as
/// "that was all of them".
const int _listed = 12;

class EgressPanel extends StatelessWidget {
  final Map<String, dynamic>? egress;
  const EgressPanel({super.key, this.egress});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final e = egress;
    if (e == null) {
      return const HairlineCard(
          child: HonestNull('The egress table has not been read yet.'));
    }
    final receipts = e['receipts'] is List
        ? (e['receipts'] as List)
            .whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList()
        : <Map<String, dynamic>>[];
    final counts =
        (e['verdict_counts'] as Map?)?.cast<String, dynamic>() ?? {};
    final rules = (e['matrix'] as Map?)?['rules'];
    final ruleCount = rules is List ? rules.length : 0;
    final strict = (e['matrix'] as Map?)?['strict'] == true;
    final unclassified = receipts
        .where((r) => _verdict(r) != 'ALLOWED')
        .toList(growable: false);
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('egress · classified against the allowlist'),
          const SizedBox(height: FwLayout.s1),
          Text(
              strict
                  ? 'Strict mode: anything no rule names is BLOCKED.'
                  : 'Non-strict mode: anything no rule names is UNKNOWN, '
                      'which is unclassified and not a pass.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          AdaptiveTiles(children: [
            StatTile(label: 'connections', value: '${e['count'] ?? 0}'),
            StatTile(
                label: 'allowed',
                value: '${counts['ALLOWED'] ?? 0}',
                status: 'verified'),
            StatTile(
                label: 'unclassified',
                value: '${unclassified.length}',
                status: unclassified.isEmpty ? 'verified' : 'unverifiable'),
            StatTile(label: 'rules', value: '$ruleCount'),
          ]),
          if (receipts.isEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('No connection was classifiable. '
                '${e['reason'] ?? 'The socket table could not be read.'}'),
          ],
          if (unclassified.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s4),
            const Kicker('not named by any rule', hot: true),
            const SizedBox(height: FwLayout.s2),
            for (final r in unclassified.take(_listed)) _row(t, r),
            if (unclassified.length > _listed)
              Text(
                  '${unclassified.length - _listed} more unclassified '
                  'connections are counted above and not listed here.',
                  style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ],
        ],
      ),
    );
  }

  static String _verdict(Map<String, dynamic> receipt) {
    final body = (receipt['seal_body'] as Map?)?.cast<String, dynamic>() ?? {};
    return '${body['verdict'] ?? 'UNKNOWN'}';
  }

  Widget _row(FwTokens t, Map<String, dynamic> receipt) {
    final body =
        (receipt['seal_body'] as Map?)?.cast<String, dynamic>() ?? {};
    final process = '${body['process'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            VerdictPill('${body['verdict'] ?? 'UNKNOWN'}',
                status: 'unverifiable'),
            const SizedBox(width: FwLayout.s3),
            Flexible(
              child: Text(
                  '${body['destination'] ?? '?'}:${body['port'] ?? '?'} '
                  '${body['protocol'] ?? ''}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 11.5, color: t.ink)),
            ),
          ]),
          Text(
              '${process.isEmpty ? 'process unnamed' : process} · '
              '${body['reason'] ?? 'no reason recorded'}',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
      ),
    );
  }
}
