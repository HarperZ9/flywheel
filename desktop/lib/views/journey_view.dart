import 'package:flutter/material.dart';

import '../controllers/journey_controller.dart';
import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/journey_cards.dart';
import '../widgets/journey_lenses.dart';

class JourneyView extends StatelessWidget {
  const JourneyView({super.key, required this.controller});
  final JourneyController controller;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) => _JourneyBody(
          state: controller.state,
          onLens: controller.selectLens,
        ),
      );
}

class _JourneyBody extends StatelessWidget {
  const _JourneyBody({required this.state, required this.onLens});
  final JourneyViewState state;
  final Future<void> Function(JourneyLens) onLens;

  @override
  Widget build(BuildContext context) {
    final projection = state.projection;
    if (projection == null) return _EmptyJourney(state: state);
    return ViewScroll(storageKey: 'journey', children: [
      SectionHeader('Evidence Journey', kicker: state.phase.name),
      const SizedBox(height: FwLayout.s4),
      JourneyCoreCard(projection: projection),
      const SizedBox(height: FwLayout.s4),
      JourneyLensSelector(
        selectedLens: state.selectedLens,
        onSelected: onLens,
        enabled: !_busy(state.phase),
      ),
      const SizedBox(height: FwLayout.s4),
      _LensSwitcher(projection: projection, lens: state.selectedLens),
      if (state.remoteFailure != null || state.localFailure != null) ...[
        const SizedBox(height: FwLayout.s4),
        _FailureSummary(state: state),
      ],
    ]);
  }
}

bool _busy(JourneyViewPhase phase) => const {
      JourneyViewPhase.loading,
      JourneyViewPhase.starting,
      JourneyViewPhase.appending,
      JourneyViewPhase.checking,
      JourneyViewPhase.cancelling,
    }.contains(phase);

class _LensSwitcher extends StatelessWidget {
  const _LensSwitcher({required this.projection, required this.lens});
  final JourneyProjection projection;
  final JourneyLens lens;

  @override
  Widget build(BuildContext context) {
    final content = switch (lens) {
      JourneyLens.rescue => RescueLens(projection: projection),
      JourneyLens.diagnose => DiagnoseLens(projection: projection),
      _ => VerifyLens(projection: projection),
    };
    return AnimatedSwitcher(
      key: const ValueKey('journey-lens-switcher'),
      duration: MediaQuery.disableAnimationsOf(context)
          ? Duration.zero
          : FwLayout.transition,
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeOutCubic,
      child: KeyedSubtree(
        key: ValueKey(lens),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [content, JourneyExtensionHost(lens: lens)],
        ),
      ),
    );
  }
}

class _EmptyJourney extends StatelessWidget {
  const _EmptyJourney({required this.state});
  final JourneyViewState state;

  @override
  Widget build(BuildContext context) {
    final detail = state.remoteFailure?.detail;
    final local = state.localFailure?.name;
    return ViewScroll(storageKey: 'journey-empty', children: [
      SectionHeader('Evidence Journey', kicker: state.phase.name),
      const SizedBox(height: FwLayout.s4),
      HonestNull(detail ??
          (local == null
              ? 'No Journey projection was supplied.'
              : 'The local Journey record could not be read: $local.')),
    ]);
  }
}

class _FailureSummary extends StatelessWidget {
  const _FailureSummary({required this.state});
  final JourneyViewState state;

  @override
  Widget build(BuildContext context) {
    final actions = state.recoveryActions.map(_recovery).join(', ');
    final failure = state.remoteFailure?.detail ??
        'The local Journey record could not be updated.';
    return HonestNull(
        actions.isEmpty ? failure : '$failure Recovery: $actions.');
  }
}

String _recovery(JourneyRecoveryAction action) => switch (action) {
      JourneyRecoveryAction.retrySameRequest => 'retry the same request',
      JourneyRecoveryAction.refreshProjection => 'refresh the projection',
      JourneyRecoveryAction.authenticate => 'authenticate',
      JourneyRecoveryAction.updateClient => 'update the client',
      JourneyRecoveryAction.reviewDraft => 'review the draft',
      JourneyRecoveryAction.chooseJourney => 'choose a Journey',
    };
