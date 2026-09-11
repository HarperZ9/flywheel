import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/journey_controller.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';
import 'fw.dart';
import 'rowan_presenter.dart';
import 'rowan_walkthrough_panel.dart';

class RowanStudioPrelude extends StatelessWidget {
  final GatewayClient? client;
  final bool alive;
  final JourneyController? journey;
  final RowanWalkthroughOperationHost? operationHost;
  final RowanWalkthroughCaptionBuilder? captionBuilder;
  final RowanWalkthroughFollowUpReviewer? onReviewFollowUp;

  const RowanStudioPrelude({
    super.key,
    required this.client,
    required this.alive,
    this.journey,
    this.operationHost,
    this.captionBuilder,
    this.onReviewFollowUp,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const RowanPresenter(),
          const SizedBox(height: FwLayout.s4),
          if (client == null)
            const HonestNull('Gateway client unavailable; live walkthrough '
                'controls are not mounted.')
          else if (operationHost == null)
            const HonestNull(
                'Shared Rowan operation controller is not composed '
                'in this checkout yet. The walkthrough scenario, oracle, and '
                'guidance shell stay draft-only until the native controller '
                'owner lands the session-lived operation host.')
          else
            RowanWalkthroughPanel(
              alive: alive,
              operationHost: operationHost!,
              journey: journey,
              captionBuilder: captionBuilder,
              onReviewFollowUp: onReviewFollowUp,
            ),
          const SizedBox(height: FwLayout.s4),
        ],
      );
}
