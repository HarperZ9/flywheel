import 'package:flutter/material.dart';
import '../controllers/studio_body_controller.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// Evidence remains inspectable beside the actual instrument output.
class StudioBodyEvidence extends StatelessWidget {
  final StudioBodyController controller;
  const StudioBodyEvidence({super.key, required this.controller});
  @override
  Widget build(BuildContext context) {
    final b = controller.binding, s = controller.snapshot;
    final status = controller.status, r = controller.lastResult;
    Widget line(String label, Object? value) => Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s1),
        child: SelectableText(
            '$label: ${value == null || value == '' ? 'not reported' : value}',
            style: fwMono(context.fw, size: 11.5, color: context.fw.inkMuted)));
    return Material(
        type: MaterialType.transparency,
        child: ExpansionTile(
            title: const Text('Observation, action and receipts'),
            children: [
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                line('Session', b.sessionRef),
                line('Screen', b.sourceRef),
                line('Delivered frame', b.latestFrameRef),
                line('Provider route', b.modelRouteRef),
                line('Model', b.model),
                if (b.frameSha256.isNotEmpty) HashText('frame', b.frameSha256),
                line('Delivery record', b.deliveryRef),
                if (b.deliveryReceiptSha256.isNotEmpty)
                  HashText('delivery', b.deliveryReceiptSha256),
                line('Observation', s?.primaryObservation?.observationRef),
                line('Capture verified by gateway', s?.captureValidated),
                line('Action target', controller.targetPreview),
                if (status != null) ...[
                  line('Authority configured', status.authority.configured),
                  line('Sound implementation declared',
                      status.built.soundEffector),
                  line('Visual implementation declared',
                      status.built.engineVisualEffector),
                  if (!status.authority.configured)
                    line('Gateway configuration',
                        status.requiredAuthorityEnv.join(', ')),
                ],
                if (r != null) ...[
                  line('Frame used for this result',
                      controller.lastResultBinding?.latestFrameRef),
                  line('Result', r.status),
                  line('Authority decision', r.authorityDecision),
                  line('Acted', r.authorityReceipt['acted']),
                  line('Verified', r.authorityReceipt['verified']),
                  if (r.receiptText('world_id').isNotEmpty)
                    line('World', r.receiptText('world_id')),
                  for (final error in r.errors) line('Error', error),
                ],
                const Text(
                    'Verification checks a named criterion. Permission to act and '
                    'a successful delivery are separate from Match, Drift or Unverifiable.'),
                const SizedBox(height: FwLayout.s2),
              ])
            ]));
  }
}
