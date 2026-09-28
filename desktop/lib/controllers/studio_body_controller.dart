import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../assistant/rowan_action_cue_complete_ids.dart';
import '../assistant/rowan_action_cue_controller.dart';
import '../assistant/rowan_action_cue_event_binding.dart';
import '../assistant/rowan_action_cue_hash.dart';
import '../assistant/rowan_action_cue_models.dart';
import '../client/studio_body_client.dart';
import '../models/studio_body_models.dart';

class StudioBodyController extends ChangeNotifier {
  final StudioBodyApi api;
  final String Function() idFactory;
  final RowanActionCueDispatch? dispatchCue;
  StudioBodyStatus? status;
  StudioBodySnapshot? snapshot;
  StudioBodyStepResult? lastResult;
  StudioBodyBinding? lastResultBinding;
  StudioBodyInstrument instrument = StudioBodyInstrument.sound;
  StudioBodyBinding binding = StudioBodyBinding.none();
  int seed = 58;
  double durationSeconds = 6;
  double rootHz = 220;
  bool busyStatus = false, busySnapshot = false, busyStep = false;
  String? error;
  bool _disposed = false;
  int _generation = 0;
  int _contextGeneration = 0;

  StudioBodyController(this.api,
      {String Function()? idFactory, this.dispatchCue})
      : idFactory = idFactory ?? _defaultId;

  bool get busy => busyStatus || busySnapshot || busyStep;
  bool get canSubmitStep =>
      !busy &&
      status?.canAttemptStep == true &&
      _snapshotMatchesBinding &&
      binding.canSubmitStep;
  bool get _snapshotMatchesBinding =>
      snapshot != null &&
      snapshot!.primaryObservation?.observationRef.isNotEmpty == true &&
      snapshot!.primaryObservation!.latestFrameRef == binding.latestFrameRef &&
      snapshot!.captureValidated &&
      snapshot!.sessionRef == binding.sessionRef &&
      snapshot!.instrumentRef == binding.instrumentRef &&
      snapshot!.sourceRef == binding.sourceRef &&
      snapshot!.frameSha256 == binding.frameSha256 &&
      snapshot!.captureSessionRef == binding.captureSessionRef &&
      snapshot!.latestFrameRef == binding.latestFrameRef;
  String get modelRouteRef => binding.modelRouteRef;
  String get targetPreview => instrument == StudioBodyInstrument.sound
      ? '$studioBodySoundTargetPrefix${binding.sessionRef}/${binding.instrumentRef}'
      : '$studioBodyEngineTargetPrefix${binding.sessionRef}/${binding.instrumentRef}';

  void updateBinding(StudioBodyBinding value) {
    if (value.identityKey == binding.identityKey) return;
    final contextChanged = value.actionContextKey != binding.actionContextKey;
    binding = value;
    _generation++;
    snapshot = null;
    if (contextChanged) {
      _contextGeneration++;
      _clearEvidence();
    }
    _notify();
  }

  void setInstrument(StudioBodyInstrument value) {
    if (instrument == value) return;
    instrument = value;
    _generation++;
    _contextGeneration++;
    _clearEvidence();
    _notify();
  }

  void setSeedText(String value) {
    seed = (int.tryParse(value.trim()) ?? seed).clamp(0, 4294967295);
    _notify();
  }

  void setDuration(double value) {
    durationSeconds = value.clamp(6, 90).roundToDouble();
    _notify();
  }

  void setRoot(double value) {
    rootHz = value.clamp(55, 880).roundToDouble();
    _notify();
  }

  Future<void> refreshStatus() async {
    if (busy) return;
    busyStatus = true;
    error = null;
    _notify();
    try {
      final next = await api.status();
      if (!_disposed) status = next;
    } catch (e) {
      if (!_disposed) error = 'body status unavailable: $e';
    } finally {
      _finish(() => busyStatus = false);
    }
  }

  Future<void> refreshSnapshot() async {
    if (busy) return;
    if (!binding.canReadSnapshot) {
      error = binding.blocker;
      snapshot = null;
      lastResult = null;
      _notify();
      return;
    }
    final generation = _generation;
    busySnapshot = true;
    error = null;
    _notify();
    try {
      final next = await api.snapshot(StudioBodySnapshotRequest(
        sessionRef: binding.sessionRef,
        instrumentRef: binding.instrumentRef,
        captureSessionRef: binding.captureSessionRef,
        sourceRef: binding.sourceRef,
        latestFrameRef: binding.latestFrameRef,
        frameSha256: binding.frameSha256,
        latestDeliveredFrameAgeMs: binding.latestDeliveredFrameAgeMs,
      ));
      if (!_stale(generation)) {
        snapshot = next;
        lastResult = null;
      }
    } catch (e) {
      if (!_stale(generation)) error = 'body snapshot unavailable: $e';
    } finally {
      _finish(() => busySnapshot = false);
    }
  }

  Future<void> submitStep() async {
    if (!canSubmitStep) return;
    final obs = snapshot!.primaryObservation!;
    final generation = _contextGeneration;
    final actionBinding = binding;
    final actionInstrument = instrument;
    final draft = _draft(obs.observationRef);
    busyStep = true;
    error = null;
    lastResult = null;
    lastResultBinding = null;
    _notify();
    _emitCue(
        actionInstrument == StudioBodyInstrument.engine
            ? RowanCompleteActionCueEvents.studioVisualPass
            : RowanCompleteActionCueEvents.studioAudioPass,
        'submit',
        draft);
    try {
      final next = await api.submitStep(draft);
      if (!_disposed && generation == _contextGeneration) {
        lastResult = next;
        lastResultBinding = actionBinding;
        if (actionInstrument == StudioBodyInstrument.engine &&
            next.actionKind == studioBodyEngineActionKind &&
            next.verifiedDelivery) {
          _emitCue(
              RowanCompleteActionCueEvents.studioRenderReview, 'review', draft);
        }
      }
    } catch (e) {
      if (!_disposed && generation == _contextGeneration) {
        error = 'body step unavailable: $e';
      }
    } finally {
      _finish(() => busyStep = false);
    }
  }

  void _emitCue(
      RowanActionCueKind kind, String phase, StudioBodyStepDraft draft) {
    final dispatch = dispatchCue;
    if (dispatch == null) return;
    final digest = rowanActionCueSha256({
      'phase': phase,
      'client_action_id': draft.clientActionId,
      'action_kind': draft.actionKind,
      'target': draft.target,
    });
    final event = RowanActionCueEvent.fromStableEvent(
      kind: kind,
      eventRef: 'studio_${phase}_${digest.substring(0, 32)}',
    );
    unawaited(_ignoreCueFailure(dispatch(event)));
  }

  Future<void> _ignoreCueFailure(Future<RowanActionCueDecision> cue) async {
    try {
      await cue;
    } catch (_) {}
  }

  StudioBodyStepDraft _draft(String observationRef) {
    final snap = snapshot;
    if (instrument == StudioBodyInstrument.engine) {
      return StudioBodyStepDraft.engine(
        clientActionId: idFactory(),
        idempotencyKey: idFactory(),
        modelRouteRef: binding.modelRouteRef,
        observationRef: observationRef,
        sessionRef: binding.sessionRef,
        instrumentRef: binding.instrumentRef,
        seed: seed,
        captureSessionRef: binding.captureSessionRef,
        latestFrameRef: binding.latestFrameRef,
        latestDeliveredFrameAgeMs: binding.latestDeliveredFrameAgeMs ??
            snap?.latestDeliveredFrameAgeMs,
        modelDelivery: binding.modelDelivery,
      );
    }
    return StudioBodyStepDraft.sound(
      clientActionId: idFactory(),
      idempotencyKey: idFactory(),
      modelRouteRef: binding.modelRouteRef,
      observationRef: observationRef,
      sessionRef: binding.sessionRef,
      instrumentRef: binding.instrumentRef,
      seed: seed,
      durationSeconds: durationSeconds,
      rootHz: rootHz,
      captureSessionRef: binding.captureSessionRef,
      latestFrameRef: binding.latestFrameRef,
      latestDeliveredFrameAgeMs:
          binding.latestDeliveredFrameAgeMs ?? snap?.latestDeliveredFrameAgeMs,
      modelDelivery: binding.modelDelivery,
    );
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    _contextGeneration++;
    super.dispose();
  }

  bool _stale(int generation) => _disposed || generation != _generation;
  void _clearEvidence() {
    snapshot = null;
    lastResult = null;
    lastResultBinding = null;
  }

  void _finish(VoidCallback change) {
    if (_disposed) return;
    change();
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }
}

String _defaultId() =>
    'ui-${DateTime.now().microsecondsSinceEpoch}-${math.Random().nextInt(1 << 32)}';
