import 'dart:async';

import '../controllers/rowan_walkthrough_operation_host.dart';
import '../models/operation_models.dart';
import 'rowan_action_cue_complete_ids.dart';
import 'rowan_action_cue_controller.dart';
import 'rowan_action_cue_event_binding_screen.dart';
import 'rowan_action_cue_models.dart';
import 'rowan_action_cue_screen_event_policy.dart';

export 'rowan_action_cue_event_binding_screen.dart';

typedef RowanActionCueDispatch = Future<RowanActionCueDecision> Function(
  RowanActionCueEvent event,
);

typedef RowanActionCueBindingErrorSink = void Function(
  Object error,
  StackTrace stackTrace,
);

final class RowanActionCueEventBinding {
  RowanActionCueEventBinding({
    required RowanWalkthroughOperationHost operationHost,
    required RowanActionCueController controller,
    RowanActionCueScreenSharingSource? screenSharing,
    RowanActionCueDispatch? dispatch,
    RowanActionCueBindingErrorSink? onError,
  })  : _operationHost = operationHost,
        _screenSharing = screenSharing,
        _controller = controller,
        _dispatch = dispatch,
        _onError = onError {
    _lastOperation = _readOperation();
    _lastScreen = _readScreen();
    _operationHost.addListener(_operationChanged);
    _screenSharing?.addListener(_screenChanged);
  }

  static const _maxRememberedEvents = 200;

  final RowanWalkthroughOperationHost _operationHost;
  final RowanActionCueScreenSharingSource? _screenSharing;
  final RowanActionCueController _controller;
  final RowanActionCueDispatch? _dispatch;
  final RowanActionCueBindingErrorSink? _onError;
  final _emittedKeys = <String>{};
  final _emittedOrder = <String>[];

  _OperationCueObservation? _lastOperation;
  RowanActionCueScreenSharingSnapshot? _lastScreen;
  final _screenPolicy = RowanActionCueScreenEventPolicy();
  var _operationLocalStartPending = false;
  var _disposed = false;

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _operationHost.removeListener(_operationChanged);
    _screenSharing?.removeListener(_screenChanged);
  }

  void _operationChanged() {
    if (_disposed) return;
    try {
      final prior = _lastOperation;
      final next = _readOperation();
      if (prior?.authorizing != true && next.authorizing) {
        _operationLocalStartPending = true;
      }
      if (_operationLocalStartPending &&
          !next.authorizing &&
          next.snapshot == null &&
          next.error != null) {
        _operationLocalStartPending = false;
      }
      final event = _operationEvent(prior, next);
      _lastOperation = next;
      if (event != null) _schedule(event);
    } on Object catch (error, stackTrace) {
      _report(error, stackTrace);
    }
  }

  void _screenChanged() {
    if (_disposed) return;
    try {
      final next = _readScreen();
      final events = _screenPolicy.events(_lastScreen, next);
      _lastScreen = next;
      _scheduleScreenInOrder(events, next);
    } on Object catch (error, stackTrace) {
      _report(error, stackTrace);
    }
  }

  _OperationCueObservation _readOperation() => _OperationCueObservation(
        snapshot: _operationHost.snapshot,
        active: _operationHost.active,
        authorizing: _operationHost.authorizing,
        error: _operationHost.error,
      );

  RowanActionCueScreenSharingSnapshot? _readScreen() =>
      _screenSharing?.cueSnapshot;

  RowanActionCueEvent? _operationEvent(
    _OperationCueObservation? prior,
    _OperationCueObservation current,
  ) {
    if (prior == current) return null;
    final snapshot = current.snapshot;
    if (snapshot == null) return null;
    final previous = prior?.snapshot;
    if (previous == snapshot) return null;
    final sameOperation = previous?.operationRef == snapshot.operationRef;
    if (previous == null) {
      if (!_operationLocalStartPending) return null;
      _operationLocalStartPending = false;
      if (snapshot.state.isTerminal) {
        return RowanActionCueEvent.fromOperationSnapshot(snapshot);
      }
      return RowanActionCueEvent.fromStableEvent(
        kind: RowanActionCueKind.operationStarted,
        eventRef: snapshot.eventHeadSha256,
        operationRef: snapshot.operationRef,
        journeyRef: snapshot.journeyRef,
        eventHeadSha256: snapshot.eventHeadSha256,
      );
    }
    if (snapshot.state.isTerminal) {
      return RowanActionCueEvent.fromOperationSnapshot(snapshot);
    }
    if (!sameOperation) {
      if (!_operationLocalStartPending) return null;
      _operationLocalStartPending = false;
      return RowanActionCueEvent.fromStableEvent(
        kind: RowanActionCueKind.operationStarted,
        eventRef: snapshot.eventHeadSha256,
        operationRef: snapshot.operationRef,
        journeyRef: snapshot.journeyRef,
        eventHeadSha256: snapshot.eventHeadSha256,
      );
    }
    if (previous.state != snapshot.state ||
        previous.eventHeadSha256 != snapshot.eventHeadSha256) {
      return RowanActionCueEvent.fromOperationSnapshot(snapshot);
    }
    return null;
  }

  void _schedule(RowanActionCueEvent event) {
    if (!_remember(event.dedupeKey)) return;
    scheduleMicrotask(() {
      if (_disposed) return;
      unawaited(_dispatchEvent(event));
    });
  }

  void _scheduleScreenInOrder(
    List<RowanActionCueEvent> events,
    RowanActionCueScreenSharingSnapshot? snapshot,
  ) {
    final pending = [
      for (final event in events)
        if (_remember(event.dedupeKey))
          _PendingScreenCue(
            event: event,
            sessionRef: snapshot?.sessionRef,
          ),
    ];
    if (pending.isEmpty) return;
    scheduleMicrotask(() async {
      for (final pendingCue in pending) {
        if (_disposed) return;
        if (!_screenCueStillCurrent(pendingCue)) {
          _forget(pendingCue.event.dedupeKey);
          continue;
        }
        await _dispatchEvent(pendingCue.event);
      }
    });
  }

  bool _screenCueStillCurrent(_PendingScreenCue pending) {
    final current = _lastScreen;
    final kind = pending.event.kind;
    if (kind == RowanCompleteActionCueEvents.modelProviderReceipt ||
        kind == RowanCompleteActionCueEvents.privacyLiveScreenOn) {
      return current?.state == RowanActionCueScreenSharingState.running &&
          current?.sessionRef == pending.sessionRef;
    }
    if (kind == RowanCompleteActionCueEvents.privacyLiveScreenOff) {
      final sessionRef = pending.sessionRef;
      if (sessionRef == null) return false;
      return current == null ||
          current.sessionRef != sessionRef ||
          current.state == RowanActionCueScreenSharingState.stopped ||
          current.state == RowanActionCueScreenSharingState.unavailable;
    }
    return true;
  }

  Future<void> _dispatchEvent(RowanActionCueEvent event) async {
    try {
      final dispatch = _dispatch ?? _controller.handle;
      await dispatch(event);
    } on Object catch (error, stackTrace) {
      _report(error, stackTrace);
    }
  }

  bool _remember(String key) {
    if (_emittedKeys.contains(key)) return false;
    _emittedKeys.add(key);
    _emittedOrder.add(key);
    if (_emittedOrder.length > _maxRememberedEvents) {
      _emittedKeys.remove(_emittedOrder.removeAt(0));
    }
    return true;
  }

  void _forget(String key) {
    if (!_emittedKeys.remove(key)) return;
    _emittedOrder.remove(key);
  }

  void _report(Object error, StackTrace stackTrace) {
    try {
      _onError?.call(error, stackTrace);
    } on Object {
      // Cue binding diagnostics must not break the UI listener dispatch path.
    }
  }
}

final class _PendingScreenCue {
  const _PendingScreenCue({
    required this.event,
    required this.sessionRef,
  });

  final RowanActionCueEvent event;
  final String? sessionRef;
}

final class _OperationCueObservation {
  const _OperationCueObservation({
    required this.snapshot,
    required this.active,
    required this.authorizing,
    required this.error,
  });

  final OperationSnapshot? snapshot;
  final bool active, authorizing;
  final String? error;

  @override
  bool operator ==(Object other) =>
      other is _OperationCueObservation &&
      snapshot == other.snapshot &&
      active == other.active &&
      authorizing == other.authorizing &&
      error == other.error;

  @override
  int get hashCode => Object.hash(snapshot, active, authorizing, error);
}
