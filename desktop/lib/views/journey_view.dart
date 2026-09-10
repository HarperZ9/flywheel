import 'package:flutter/material.dart';

import '../controllers/journey_controller.dart';
import '../models/journey_models.dart';
import '../navigation/app_route.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/flywheel_nav.dart';
import '../widgets/fw.dart';
import '../widgets/journey_cards.dart';
import '../widgets/journey_lenses.dart';

class JourneyView extends StatelessWidget {
  const JourneyView({
    super.key,
    required this.controller,
    this.alive = true,
    this.onStartEngine,
  });
  final JourneyController controller;
  final bool alive;
  final VoidCallback? onStartEngine;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) => _JourneyBody(
          state: controller.state,
          onLens: controller.selectLens,
          alive: alive,
          onStartEngine: onStartEngine,
        ),
      );
}

class _JourneyBody extends StatelessWidget {
  const _JourneyBody({
    required this.state,
    required this.onLens,
    required this.alive,
    required this.onStartEngine,
  });
  final JourneyViewState state;
  final Future<void> Function(JourneyLens) onLens;
  final bool alive;
  final VoidCallback? onStartEngine;

  @override
  Widget build(BuildContext context) {
    final projection = state.projection;
    if (projection == null) {
      return _EmptyJourney(
          state: state, alive: alive, onStartEngine: onStartEngine);
    }
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
  const _EmptyJourney({
    required this.state,
    required this.alive,
    required this.onStartEngine,
  });
  final JourneyViewState state;
  final bool alive;
  final VoidCallback? onStartEngine;

  @override
  Widget build(BuildContext context) {
    final detail = state.remoteFailure?.detail;
    final local = state.localFailure?.name;
    final loading = detail == null && local == null && _busy(state.phase);
    return ViewScroll(storageKey: 'journey-empty', children: [
      SectionHeader('Evidence Journey', kicker: state.phase.name),
      const SizedBox(height: FwLayout.s4),
      if (loading)
        const Center(
            child: Padding(
          padding: EdgeInsets.all(FwLayout.s4),
          child: CircularProgressIndicator(strokeWidth: 2),
        ))
      else
        HonestNull(detail ??
            (local == null
                ? 'No Journey projection was supplied.'
                : 'The local Journey record could not be read: $local.')),
      const SizedBox(height: FwLayout.s4),
      JourneyStartCard(alive: alive, onStartEngine: onStartEngine),
    ]);
  }
}

class JourneyStartCard extends StatelessWidget {
  const JourneyStartCard({
    super.key,
    required this.alive,
    this.onStartEngine,
  });
  final bool alive;
  final VoidCallback? onStartEngine;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('start here', hot: true),
        const SizedBox(height: FwLayout.s2),
        Text('Get to the first verified run',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: FwLayout.s2),
        Text(
          'Connect the engine, choose a model, register work, then run '
          'through Chat, Plan, or Code. Receipts keep the proof.',
          style: TextStyle(fontSize: 12.5, height: 1.45, color: t.inkMuted),
        ),
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          if (!alive && onStartEngine != null)
            FilledButton(
              onPressed: onStartEngine,
              child: const Text('Start engine'),
            ),
          _route(context, 'Models setup', DestinationId.models),
          _route(context, 'Projects', DestinationId.projects),
          _route(context, 'Chat', DestinationId.chat),
          _route(context, 'Plan', DestinationId.plan),
          _route(context, 'Code', DestinationId.code),
          _route(context, 'Receipts', DestinationId.receipts),
        ]),
      ]),
    );
  }

  Widget _route(BuildContext context, String label, DestinationId id) =>
      OutlinedButton(
        onPressed: FlywheelNav.of(context) == null
            ? null
            : () => FlywheelNav.jump(context, id),
        child: Text(label),
      );
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
