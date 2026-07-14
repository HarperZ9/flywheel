// run_evidence_card.dart — everything a finished run can prove about
// itself, in one card: duration and the TTVA null or number, the window
// (what the model read), risk demands, workspace change verdict, and the
// gateway countersignature into the audit chain. Rendered as-is from the
// run document; the client computes nothing.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class RunEvidenceCard extends StatelessWidget {
  final Map<String, dynamic> run;
  const RunEvidenceCard({super.key, required this.run});

  Map<String, dynamic> _map(String key) =>
      run[key] is Map<String, dynamic> ? run[key] as Map<String, dynamic> : const {};

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final manifest = _map('context_manifest');
    final risk = _map('risk_review');
    final receipt = _map('run_receipt');
    final workspace = _map('workspace');
    final effort = _map('effort');
    final ttva = run['ttva_s'];
    final rows = <(String, String, String?)>[
      if (run['duration_s'] != null)
        ('duration', '${run['duration_s']}s', null),
      (
        'ttva',
        ttva == null ? 'null: nothing verified' : '${ttva}s',
        ttva == null ? 'unverifiable' : 'verified'
      ),
      if (effort.isNotEmpty)
        ('effort', '${effort['name']} · ${effort['max_steps']} steps', null),
      if (manifest.isNotEmpty)
        ('window',
         '${(manifest['reads'] as List?)?.length ?? 0} reads · '
             '${(manifest['tools'] as Map?)?.length ?? 0} tools',
         null),
      if (risk.isNotEmpty)
        (
          'risk',
          (risk['demands'] as List?)?.isEmpty ?? true
              ? 'no high-tier edits'
              : '${(risk['demands'] as List).length} high-tier '
                  'edit(s) demand a full walk',
          (risk['demands'] as List?)?.isEmpty ?? true ? null : 'drift'
        ),
      if (workspace.isNotEmpty)
        (
          'workspace',
          workspace['changed'] == true ? 'changed' : 'unchanged',
          workspace['changed'] == true ? 'drift' : 'verified'
        ),
    ];
    return HairlineCard(
      recessed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('run evidence'),
          const SizedBox(height: FwLayout.s2),
          for (final (label, value, status) in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                SizedBox(
                    width: 84,
                    child: Text(label,
                        style: fwMono(t, size: 11, color: t.inkFaint))),
                if (status != null) ...[
                  VerdictDot(status, size: 6),
                  const SizedBox(width: 6),
                ],
                Expanded(
                    child:
                        Text(value, style: fwMono(t, size: 11.5))),
              ]),
            ),
          if (receipt['chain_hash'] != null &&
              '${receipt['chain_hash']}'.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            HashText('countersigned', '${receipt['chain_hash']}'),
          ],
        ],
      ),
    );
  }
}
