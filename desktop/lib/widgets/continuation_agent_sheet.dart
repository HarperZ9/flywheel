import 'dart:async';

import 'package:flutter/material.dart';

import '../client/continuation_api.dart';
import '../client/gateway_client.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../ide/agent_panel.dart';
import '../models/continuation_models.dart';

/// Opens the existing agent surface with a Journey-bound continuation handoff.
Future<void> showContinuationAgentSheet({
  required BuildContext context,
  required GatewayClient client,
  required JourneyController journey,
  required bool alive,
  required ContinuationPreview preview,
  required ContinuationStartResult started,
}) async {
  final operationScope = GatewayOperationScope.maybeOf(context);
  if (operationScope == null) {
    throw StateError('gateway operation scope unavailable');
  }
  await journey.openSession(started.journey.journeyRef, started.openLens);
  final privateContext = await GatewayContinuationApi(
    client,
  ).privateContext(preview);
  if (!context.mounted) return;
  final goal = TextEditingController(text: privateContext.runner.goal);
  try {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => GatewayOperationScope(
        authorize: operationScope.authorize,
        child: SafeArea(
          child: FractionallySizedBox(
            heightFactor: .9,
            child: AgentPanel(
              client: client,
              alive: alive,
              workspaceRoot: privateContext.runner.root,
              goalController: goal,
              continuationHandoff: privateContext.agentHandoff(preview),
              onRunStarted: () {},
              onRunFinished: () => unawaited(journey.refreshActiveProjection()),
            ),
          ),
        ),
      ),
    );
  } finally {
    goal.dispose();
  }
}
