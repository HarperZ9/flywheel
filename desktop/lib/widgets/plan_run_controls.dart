import 'package:flutter/material.dart';

import '../controllers/plan_controller.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

export '../controllers/plan_controller.dart'
    show planRunCompletionCopy, planRunDriftCopy;

String? _status(PlanController controller) => switch (controller.phase) {
      PlanPhase.idle => null,
      PlanPhase.forging => 'Forging the exact Plan contract…',
      PlanPhase.ready => controller.failureMessage ??
          'Forged contract ready for one exact approval.',
      PlanPhase.approvalRequired => 'Approval required for this exact run.',
      PlanPhase.running => 'Running the approved forged contract…',
      PlanPhase.completed => controller.completionMessage,
      PlanPhase.drift || PlanPhase.failed => controller.failureMessage,
    };

final class PlanRunControls extends StatelessWidget {
  final PlanController controller;
  final bool canForge, canRun;
  final String runLabel;
  final VoidCallback onForge, onRun;

  const PlanRunControls(
      {super.key,
      required this.controller,
      required this.canForge,
      required this.canRun,
      required this.runLabel,
      required this.onForge,
      required this.onRun});

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final busy = const {
            PlanPhase.forging,
            PlanPhase.approvalRequired,
            PlanPhase.running
          }.contains(controller.phase);
          final status = _status(controller);
          final failed = const {PlanPhase.drift, PlanPhase.failed}
              .contains(controller.phase);
          return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  FilledButton(
                      onPressed: canForge && !busy ? onForge : null,
                      child: Text(controller.phase == PlanPhase.forging
                          ? 'Forging…'
                          : 'Forge plan')),
                  const SizedBox(width: FwLayout.s3),
                  OutlinedButton(
                      onPressed: canRun && !busy ? onRun : null,
                      child: Text(controller.phase == PlanPhase.running
                          ? 'Running…'
                          : runLabel)),
                ]),
                if (status != null) ...[
                  const SizedBox(height: FwLayout.s2),
                  failed
                      ? HonestNull(status)
                      : Text(status,
                          style: fwMono(context.fw,
                              size: 11.5, color: context.fw.inkMuted)),
                ],
              ]);
        },
      );
}
