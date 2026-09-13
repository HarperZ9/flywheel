import 'package:flutter/material.dart';

import '../models/process_audit_review.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ProcessAuditGatewayEffectView extends StatelessWidget {
  final GatewayEffectOfflineReview review;
  const ProcessAuditGatewayEffectView({super.key, required this.review});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('offline gateway evidence'),
      const SizedBox(height: FwLayout.s2),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        VerdictPill(
            'Internal consistency ${review.internalConsistency.verdict}',
            status: _status(review.internalConsistency.verdict)),
        VerdictPill(
            'Reference correspondence ${review.expectedCorrespondence.verdict}',
            status: _status(review.expectedCorrespondence.verdict)),
        VerdictPill('Effect coverage ${review.effectCoverage.verdict}',
            status: _status(review.effectCoverage.verdict)),
        const VerdictPill('Semantic correctness UNVERIFIABLE',
            status: 'unverifiable'),
      ]),
      const SizedBox(height: FwLayout.s2),
      Text(
        'Internal consistency checks the submitted terminal result, lifecycle '
        'history, trace records, and packet-local digests. Reference '
        'correspondence uses only separately supplied expected hashes.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s3),
      _expected(t),
      const SizedBox(height: FwLayout.s3),
      _coverage(t),
      const SizedBox(height: FwLayout.s3),
      _semantic(),
    ]);
  }

  Widget _expected(FwTokens t) {
    final expected = review.expectedCorrespondence;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('reference correspondence'),
      const SizedBox(height: FwLayout.s1),
      Text('Reference provenance ${expected.referenceProvenance}.',
          style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
      if (expected.checks.isEmpty)
        const HonestNull(
            'No separately supplied expected hashes were reviewed.')
      else
        for (final check in expected.checks)
          Padding(
            padding: const EdgeInsets.only(top: FwLayout.s1),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${check.artifact} ${check.verdict}',
                  style: fwMono(t, size: 11.5, color: t.ink)),
              Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s1, children: [
                HashText('expected', check.expectedSha256, keep: 16),
                HashText('computed', check.computedSha256, keep: 16),
              ]),
            ]),
          ),
      for (final limit in expected.limits)
        Padding(
          padding: const EdgeInsets.only(top: FwLayout.s1),
          child: Text('- $limit'),
        ),
    ]);
  }

  Widget _coverage(FwTokens t) {
    final coverage = review.effectCoverage;
    if (coverage.verdict != 'MATCH') {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('effect coverage'),
        const SizedBox(height: FwLayout.s1),
        for (final limit in coverage.limits)
          Padding(
            padding: const EdgeInsets.only(bottom: FwLayout.s1),
            child: Text('- $limit'),
          ),
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('effect coverage'),
      const SizedBox(height: FwLayout.s1),
      Text(
        '${coverage.retainedObservations} retained observations, '
        '${coverage.omittedObservations} omitted by cap.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      Text('Unknown scope ${_unknownSummary(coverage.unobservedScope)}.',
          style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
      SelectableText('Raw unknown scope ${coverage.unobservedScope.join(', ')}',
          style: fwMono(t, size: 11)),
      Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s1, children: [
        HashText('trace head', coverage.traceHeadSha256, keep: 16),
        HashText('observations', coverage.knownObservationsDigest, keep: 16),
      ]),
      Text(
        'Action witness ${coverage.actionWitness.status}; tool receipts '
        '${coverage.toolCallReceipts.status}.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      for (final item in coverage.knownObservations)
        Padding(
          padding: const EdgeInsets.only(top: FwLayout.s1),
          child: SelectableText(
            'trace_sequence ${item.traceSequence} · ${item.recordKind} · '
            '${item.jsonPointer}\nrecord ${item.recordSha256}\n'
            'value ${item.valueSha256}',
            style: fwMono(t, size: 11),
          ),
        ),
    ]);
  }

  Widget _semantic() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('semantic limits'),
          const SizedBox(height: FwLayout.s1),
          for (final limit in review.semanticCorrectness.doesNotVerify)
            Padding(
              padding: const EdgeInsets.only(bottom: FwLayout.s1),
              child: Text('does not verify $limit'),
            ),
        ],
      );

  String _status(String value) => switch (value) {
        'MATCH' => 'verified',
        'DRIFT' => 'drift',
        _ => 'unverifiable',
      };

  String _unknownSummary(List<String> codes) {
    final labels = <String>[
      if (codes.contains('NOT_ROLLBACK')) 'no rollback proof',
      if (codes.contains('NOT_EFFECT_ABSENCE')) 'no effect-absence proof',
      if (codes.contains('NOT_CURRENT_FILESYSTEM_STATE')) 'not current state',
      if (codes.contains('UNRECORDED_ACTIONS_NOT_EXCLUDED'))
        'unrecorded actions remain possible',
      if (codes
          .contains('TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN'))
        'unfingerprinted tools remain unknown',
      if (codes.contains('EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN'))
        'later effects remain unknown',
    ];
    return labels.isEmpty ? 'unknown' : labels.join('; ');
  }
}
