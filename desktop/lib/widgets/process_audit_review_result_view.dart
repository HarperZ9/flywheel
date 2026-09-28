import 'package:flutter/material.dart';

import '../models/process_audit_review.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'process_audit_gateway_effect_view.dart';

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
      if (result.gatewayEffect != null) ...[
        const SizedBox(height: FwLayout.s3),
        ProcessAuditGatewayEffectView(review: result.gatewayEffect!),
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
                if (pointer.isDerived) 'DERIVED',
                if (pointer.source.isNotEmpty) pointer.source,
                if (pointer.privacy.isNotEmpty) pointer.privacy,
                if (pointer.sourcePointer != pointer.pointer)
                  'source ${pointer.sourcePointer}',
                if (pointer.location != null) pointer.location!.label,
                pointer.preview,
                ...pointer.limits,
              ].join(' · '),
              style: TextStyle(fontSize: 12, color: t.inkMuted),
            ),
            children: [
              if (pointer.source.isNotEmpty ||
                  pointer.privacy.isNotEmpty ||
                  pointer.limits.isNotEmpty)
                _block(t, 'source metadata', _metadata(pointer)),
              _block(t, 'source value', pointer.sourceValueText),
              if (pointer.isDerived)
                _PrivateSourceContext(pointer: pointer)
              else
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

  String _metadata(ProcessAuditSourcePointer pointer) => [
        if (pointer.isDerived) 'DERIVED',
        if (pointer.source.isNotEmpty) 'source: ${pointer.source}',
        if (pointer.privacy.isNotEmpty) 'privacy: ${pointer.privacy}',
        if (pointer.sourcePointer != pointer.pointer)
          'source pointer: ${pointer.sourcePointer}',
        for (final limit in pointer.limits) 'limit: $limit',
      ].join('\n');

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

class _PrivateSourceContext extends StatefulWidget {
  final ProcessAuditSourcePointer pointer;
  const _PrivateSourceContext({required this.pointer});

  @override
  State<_PrivateSourceContext> createState() => _PrivateSourceContextState();
}

class _PrivateSourceContextState extends State<_PrivateSourceContext> {
  bool _shown = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Align(
      alignment: Alignment.centerLeft,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextButton.icon(
          onPressed: () => setState(() => _shown = !_shown),
          icon: const Icon(Icons.lock_open_outlined, size: 16),
          label: Text(_shown
              ? 'Hide private source context'
              : 'Show private source context'),
        ),
        if (_shown) ...[
          const Kicker('private source context'),
          const SizedBox(height: FwLayout.s1),
          SelectableText(
            widget.pointer.location?.context ?? 'offset unavailable locally',
            style: fwMono(t, size: 11, color: t.inkSoft),
          ),
        ],
      ]),
    );
  }
}
