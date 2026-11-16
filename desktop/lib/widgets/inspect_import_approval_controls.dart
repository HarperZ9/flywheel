import 'package:flutter/material.dart';

import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../models/inspect_evidence_upload.dart';
import '../models/journey_models.dart';
import '../navigation/app_route.dart';
import 'flywheel_nav.dart';
import 'fw.dart';

class InspectImportApprovalControls extends StatelessWidget {
  const InspectImportApprovalControls({
    super.key,
    required this.busy,
    required this.upload,
    required this.onPick,
    required this.onPickUnitContract,
    required this.onRequestApproval,
    this.journey,
  });

  final bool busy;
  final InspectEvidenceUpload? upload;
  final JourneyController? journey;
  final VoidCallback onPick;
  final VoidCallback onPickUnitContract;
  final VoidCallback onRequestApproval;

  @override
  Widget build(BuildContext context) {
    final scopedJourney =
        journey ?? GatewayOperationScope.maybeOf(context)?.journey;
    if (scopedJourney == null) return _controls(context, true);
    return AnimatedBuilder(
      animation: scopedJourney,
      builder: (context, _) {
        final state = scopedJourney.state;
        final ready = _hasCurrentJourney(state);
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _controls(context, ready),
          if (upload != null) ...[
            const SizedBox(height: FwLayout.s3),
            _JourneyPrerequisite(journey: scopedJourney, ready: ready),
          ],
        ]);
      },
    );
  }

  Widget _controls(BuildContext context, bool journeyReady) => Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s2,
        children: [
          OutlinedButton(
            onPressed: busy ? null : onPick,
            child: Text(busy ? 'Working...' : 'Select Inspect JSON'),
          ),
          OutlinedButton(
            onPressed: busy || upload == null ? null : onPickUnitContract,
            child: const Text('Select scorer unit sidecar'),
          ),
          FilledButton(
            onPressed: busy || upload == null || !journeyReady
                ? null
                : onRequestApproval,
            child: const Text('Request approval'),
          ),
        ],
      );
}

class _JourneyPrerequisite extends StatelessWidget {
  const _JourneyPrerequisite({required this.journey, required this.ready});
  final JourneyController journey;
  final bool ready;

  @override
  Widget build(BuildContext context) {
    final state = journey.state;
    if (ready) {
      return Text(
        'Approval will bind to Journey ${state.activeJourneyRef}.',
        style: Theme.of(context).textTheme.bodySmall,
      );
    }
    final nav = FlywheelNav.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const HonestNull('Select or create a Journey before approval.'),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s2,
          runSpacing: FwLayout.s2,
          children: [
            OutlinedButton(
              onPressed: nav == null
                  ? null
                  : () => FlywheelNav.jump(context, DestinationId.journey),
              child: const Text('Open Journey'),
            ),
            for (final item in state.journeys.take(3))
              OutlinedButton(
                onPressed: () async {
                  await journey.openSession(
                    item.journeyRef,
                    item.lens ?? JourneyLens.verify,
                  );
                },
                child: Text('Use Journey ${_shortRef(item.journeyRef)}'),
              ),
          ],
        ),
      ],
    );
  }
}

bool _hasCurrentJourney(JourneyViewState state) {
  final active = state.projection;
  return active != null &&
      !active.invalidResponse &&
      state.activeJourneyRef == active.journeyRef;
}

String _shortRef(String ref) =>
    ref.length <= 12 ? ref : '${ref.substring(0, 12)}...';
