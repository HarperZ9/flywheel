import 'dart:convert';

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// Flips one hex char of a seal COPY for tamper demonstration.
/// The stored receipt is never touched.
Map<String, dynamic> flipOneHexChar(Map<String, dynamic> receipt) {
  final copy = jsonDecode(jsonEncode(receipt)) as Map<String, dynamic>;
  final seal = copy['seal'];
  final hex = (seal is Map ? seal['hex'] : null);
  if (hex is String && hex.isNotEmpty) {
    seal['hex'] = (hex[0] == '0' ? '1' : '0') + hex.substring(1);
  }
  return copy;
}

/// MATCH -> accept; TAMPERED -> hot mark; else unproven.
String verifyVerdictStatus(String verdict) =>
    {'MATCH': 'verified', 'TAMPERED': 'drift'}[verdict.toUpperCase()] ??
    'unverifiable';

/// The MATCH branch: accept color, the seal held.
class VerifyStateRow extends StatelessWidget {
  final Map<String, dynamic> doc;
  final String? chainLabel;
  final String? chainHash;
  const VerifyStateRow({
    super.key,
    required this.doc,
    this.chainLabel,
    this.chainHash,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final verdict = '${doc['verdict'] ?? ''}';
    final status = verifyVerdictStatus(verdict);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        VerdictDot(status, size: 8),
        const SizedBox(width: FwLayout.s2),
        VerdictPill(verdict.toLowerCase(), status: status),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text('${doc['detail'] ?? ''}',
              style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ),
      ]),
      if (verdict.toUpperCase() == 'MATCH' &&
          chainLabel != null &&
          (chainHash?.isNotEmpty ?? false)) ...[
        const SizedBox(height: FwLayout.s2),
        HashText(chainLabel!, chainHash!, keep: 24),
      ],
    ]);
  }
}

/// The TAMPERED branch: hot mark that NAMES the failing check.
class TamperStateCard extends StatelessWidget {
  final Map<String, dynamic> doc;
  const TamperStateCard({super.key, required this.doc});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final verdict = '${doc['verdict'] ?? ''}';
    final failure = '${doc['failure_class'] ?? ''}';
    return Container(
      padding: const EdgeInsets.all(FwLayout.s3),
      decoration: BoxDecoration(
        color: t.drift.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.drift.withValues(alpha: 0.45)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const VerdictDot('tampered', size: 8),
          const SizedBox(width: FwLayout.s2),
          VerdictPill(
              failure.isEmpty ? verdict.toLowerCase() : 'tampered · $failure',
              status: 'drift'),
        ]),
        const SizedBox(height: FwLayout.s2),
        Text('One flipped byte, refused. ${doc['detail'] ?? ''}',
            style: fwMono(t, size: 11, color: t.inkSoft)),
      ]),
    );
  }
}
