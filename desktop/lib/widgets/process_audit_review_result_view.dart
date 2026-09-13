import 'package:flutter/material.dart';

import '../models/process_audit_review.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ProcessAuditReviewResultView extends StatelessWidget {
  final ProcessAuditReviewResult result;
  const ProcessAuditReviewResultView({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (result.errorCode != null) {
      return HonestNull('${result.errorCode}: ${result.errorMessage}');
    }
    final source = result.source;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        VerdictPill(result.packetIntegrityLabel,
            status: result.packetIntegrityStatus),
        const VerdictPill('Semantic UNVERIFIABLE', status: 'unverifiable'),
        VerdictPill('Declared access ${result.declaredAccess.verdict}',
            status: _status(result.declaredAccess.verdict)),
      ]),
      if (source != null) ...[
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          HashText('source', source.sha256, keep: 24),
          Text('${source.byteLength} bytes',
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
        ]),
      ],
      const SizedBox(height: FwLayout.s3),
      Text(
        'Declared access coverage '
        '${_plain(result.declaredAccess.coverageAssessment)}. '
        'This checks retained declared records against the packet inventory; '
        'it does not establish actual lab access.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      if (result.declaredAccess.reportedCoverageAssessment.isNotEmpty)
        Text(
          'Reported coverage '
          '${_plain(result.declaredAccess.reportedCoverageAssessment)}.',
          style: TextStyle(fontSize: 12.5, color: t.inkMuted),
        ),
      const SizedBox(height: FwLayout.s3),
      _verification(t),
      const SizedBox(height: FwLayout.s3),
      _pointers(t),
      const SizedBox(height: FwLayout.s3),
      _limits(),
    ]);
  }

  Widget _verification(FwTokens t) {
    final v = result.verification;
    final rows = {
      'packet digest': v.packetDigest,
      'evaluation': v.evaluationDigest,
      'source values': v.sourceValuesDigest,
      'independence': v.independenceDigest,
      'actions': v.actionChain,
      'work receipt': v.workReceipt,
      'audit receipt': v.audit,
      'audit subject': v.auditSubject,
      'receipt verification': v.receiptVerification,
      'declared access': v.accessVerdict,
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('packet integrity'),
      const SizedBox(height: FwLayout.s2),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        for (final entry in rows.entries)
          VerdictPill('${entry.key} ${entry.value}',
              status: _status(entry.value)),
      ]),
      if (v.failedFields.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        const Kicker('checked fields with drift'),
        const SizedBox(height: FwLayout.s1),
        for (final field in v.failedFields.take(4))
          Text('${field.field} ${field.check}',
              style: fwMono(t, size: 11, color: t.inkMuted)),
      ],
    ]);
  }

  Widget _pointers(FwTokens t) {
    if (result.sourcePointers.isEmpty) {
      return const HonestNull('No packet source pointers were reported.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('source pointers'),
      const SizedBox(height: FwLayout.s2),
      for (final pointer in result.sourcePointers)
        Material(
          type: MaterialType.transparency,
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(bottom: FwLayout.s3),
            title: Text(pointer.pointer,
                style: fwMono(t, size: 11.5, color: t.ink)),
            subtitle: Text(
              [
                if (pointer.location != null) pointer.location!.label,
                pointer.preview,
              ].join(' · '),
              style: TextStyle(fontSize: 12, color: t.inkMuted),
            ),
            children: [
              _block(t, 'source value', pointer.sourceValueText),
              _block(
                t,
                'local context',
                pointer.location?.context ?? 'offset unavailable locally',
              ),
            ],
          ),
        ),
    ]);
  }

  Widget _block(FwTokens t, String label, String value) => Align(
        alignment: Alignment.centerLeft,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Kicker(label),
          const SizedBox(height: FwLayout.s1),
          SelectableText(value, style: fwMono(t, size: 11, color: t.inkSoft)),
        ]),
      );

  Widget _limits() {
    final limits = [
      ...result.declaredAccess.limits,
      ...result.limitations,
    ];
    if (limits.isEmpty) return const HonestNull('No limits were reported.');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('limits'),
      const SizedBox(height: FwLayout.s2),
      for (final limit in limits)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s1),
          child: Text('- $limit'),
        ),
    ]);
  }

  String _plain(String value) => value.replaceAll('_', ' ');
  String _status(String value) => switch (value) {
        'MATCH' => 'verified',
        'DRIFT' => 'drift',
        _ => 'unverifiable',
      };
}
