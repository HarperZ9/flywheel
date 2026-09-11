import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/journey_controller.dart';
import 'fw.dart';
import 'rowan_presenter.dart';
import 'rowan_walkthrough_panel.dart';

class RowanStudioPrelude extends StatelessWidget {
  final GatewayClient? client;
  final bool alive;
  final JourneyController? journey;
  final RowanWalkthroughCaptionBuilder? captionBuilder;
  final RowanWalkthroughFollowUpReviewer? onReviewFollowUp;

  const RowanStudioPrelude({
    super.key,
    required this.client,
    required this.alive,
    this.journey,
    this.captionBuilder,
    this.onReviewFollowUp,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const RowanPresenter(),
          if (client == null) ...[
            const SizedBox(height: FwLayout.s4),
            const HonestNull('Gateway client unavailable; live walkthrough '
                'controls are not mounted.'),
          ] else ...[
            const SizedBox(height: FwLayout.s4),
            RowanWalkthroughPanel(
              client: client!,
              alive: alive,
              journey: journey,
              captionBuilder: captionBuilder,
              onReviewFollowUp: onReviewFollowUp,
            ),
          ],
          const SizedBox(height: FwLayout.s4),
        ],
      );
}
