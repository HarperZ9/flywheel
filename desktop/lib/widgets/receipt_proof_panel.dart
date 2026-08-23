// receipt_proof_panel.dart -- renders one inclusion-proof request and its
// on-device verification outcome. The panel never labels a served proof
// verified: MATCH appears only when verifyReceiptProof recomputes the
// Merkle root on this device, drift and unverifiable render as honest
// failures. Presentation only; all truth comes from lib/models/receipt_proof.dart.

import 'package:flutter/material.dart';

import '../models/receipt_proof.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ReceiptProofPanel extends StatelessWidget {
  final String? leaf;
  final Map<String, dynamic>? proof;
  final bool proving;
  final String? error;

  const ReceiptProofPanel({
    super.key,
    required this.leaf,
    required this.proof,
    required this.proving,
    required this.error,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Semantics(
      label: 'Inclusion proof for receipt ${leaf ?? ''}',
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText('leaf  ${leaf ?? ''}',
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
            const SizedBox(height: FwLayout.s2),
            if (proving)
              Row(children: [
                const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: FwLayout.s2),
                Text('walking the log…',
                    style: fwMono(t, size: 11.5, color: t.inkMuted)),
              ])
            else if (error != null)
              HonestNull(error!)
            else
              _verdictBody(context),
          ],
        ),
      ),
    );
  }

  Widget _verdictBody(BuildContext context) {
    final t = context.fw;
    if (proof == null) {
      return const HonestNull('No proof object was returned for this leaf.');
    }
    final parsed = ReceiptProof.fromJson(proof!);
    if (parsed == null) {
      return const HonestNull(
          'This proof does not read as a flywheel.receipts-proof/v2 '
          'document; it cannot be verified on this device.');
    }
    final r = verifyReceiptProof(parsed);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          switch (r.verdict) {
            ReceiptProofVerdict.match =>
              const VerdictPill('included', status: 'verified'),
            ReceiptProofVerdict.drift =>
              const VerdictPill('drift', status: 'drift'),
            ReceiptProofVerdict.unverifiable =>
              const VerdictPill('unverifiable', status: 'unverifiable'),
          },
          const SizedBox(width: FwLayout.s2),
          Text('index ${parsed.index} of ${parsed.treeSize}',
              style: fwMono(t, size: 11.5, color: t.inkMuted)),
        ]),
        const SizedBox(height: FwLayout.s2),
        Text(r.detail,
            style: fwMono(t, size: 10.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s2),
        SelectableText('merkle root  ${parsed.merkleRoot}',
            style: fwMono(t, size: 11, color: t.inkSoft)),
      ],
    );
  }
}
