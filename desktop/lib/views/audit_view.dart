// audit_view.dart — the Audit destination: a receipt-chained post-work reviewer.
//
// Layer 2 to the eval receipt's Layer 1. Paste a sealed work receipt, run a
// cheap domain-agnostic review, and get a SEPARATE developer-facing judgment —
// reviews across neutral dimensions, a bounded verdict, a confidence, and an
// honest-null does_not_prove — sealed into an audit receipt CHAINED onto the
// work. Verify it offline; the chain proves it reviewed THAT exact work, and
// corrupting one byte makes the same verifier refuse. This view is a thin wire:
// it hands the client's typed audit methods to the dumb panel.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/audit_receipt_panel.dart';
import '../widgets/fw.dart';
import '../widgets/suite_audit_panel.dart';

class AuditView extends StatelessWidget {
  final GatewayClient client;
  final bool alive;
  const AuditView({super.key, required this.client, required this.alive});

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty(
          'The engine is offline. Audit a work receipt once it is up.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'audit', children: [
      const SectionHeader('The audit layer', kicker: 'audit'),
      const SizedBox(height: FwLayout.s3),
      Text(
        'A cheap post-work reviewer reads a completed work receipt and renders a '
        'SEPARATE judgment: reviews across neutral dimensions, a bounded verdict '
        'with a confidence, and an honest-null. It seals that judgment into a '
        'receipt CHAINED onto the work, so the review is as verifiable as the '
        'thing it reviews. An audit is an opinion with a confidence, not a proof.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s5),
      AuditReceiptPanel(
        onRun: (workReceipt) => client.auditRun(workReceipt),
        onVerify: (auditReceipt, workReceipt) =>
            client.auditVerify(auditReceipt, workReceipt: workReceipt),
      ),
      const SizedBox(height: FwLayout.s5),
      SuiteAuditPanel(client: client),
    ]);
  }
}
