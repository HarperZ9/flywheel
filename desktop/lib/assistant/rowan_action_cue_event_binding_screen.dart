import 'package:flutter/foundation.dart';

enum RowanActionCueScreenSharingState {
  stopped,
  starting,
  running,
  paused,
  disconnected,
  unavailable,
}

enum RowanActionCueObservationOrigin {
  observed,
  localStart,
  recovered,
}

abstract interface class RowanActionCueScreenSharingSource
    implements Listenable {
  RowanActionCueScreenSharingSnapshot get cueSnapshot;
}

final class RowanActionCueScreenSharingListenableSource
    implements RowanActionCueScreenSharingSource {
  const RowanActionCueScreenSharingListenableSource({
    required Listenable listenable,
    required RowanActionCueScreenSharingSnapshot Function() readSnapshot,
  })  : _listenable = listenable,
        _readSnapshot = readSnapshot;

  final Listenable _listenable;
  final RowanActionCueScreenSharingSnapshot Function() _readSnapshot;

  @override
  RowanActionCueScreenSharingSnapshot get cueSnapshot => _readSnapshot();

  @override
  void addListener(VoidCallback listener) => _listenable.addListener(listener);

  @override
  void removeListener(VoidCallback listener) =>
      _listenable.removeListener(listener);
}

final class RowanActionCueScreenSharingSnapshot {
  const RowanActionCueScreenSharingSnapshot._({
    required this.state,
    this.sessionRef,
    this.error,
    this.uncertainOpen = false,
    this.busy = false,
    this.origin = RowanActionCueObservationOrigin.observed,
  });

  const RowanActionCueScreenSharingSnapshot.stopped({
    String? sessionRef,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) : this._(
          state: RowanActionCueScreenSharingState.stopped,
          sessionRef: sessionRef,
          origin: origin,
        );

  const RowanActionCueScreenSharingSnapshot.starting({
    String? sessionRef,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.localStart,
  }) : this._(
          state: RowanActionCueScreenSharingState.starting,
          sessionRef: sessionRef,
          busy: true,
          origin: origin,
        );

  const RowanActionCueScreenSharingSnapshot.running({
    required String sessionRef,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) : this._(
          state: RowanActionCueScreenSharingState.running,
          sessionRef: sessionRef,
          origin: origin,
        );

  const RowanActionCueScreenSharingSnapshot.paused({
    required String sessionRef,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) : this._(
          state: RowanActionCueScreenSharingState.paused,
          sessionRef: sessionRef,
          origin: origin,
        );

  const RowanActionCueScreenSharingSnapshot.disconnected({
    required String sessionRef,
    String? error,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) : this._(
          state: RowanActionCueScreenSharingState.disconnected,
          sessionRef: sessionRef,
          error: error,
          origin: origin,
        );

  const RowanActionCueScreenSharingSnapshot.unavailable({
    String? error,
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) : this._(
          state: RowanActionCueScreenSharingState.unavailable,
          error: error,
          origin: origin,
        );

  factory RowanActionCueScreenSharingSnapshot.recoveredRunning({
    required String sessionRef,
  }) =>
      RowanActionCueScreenSharingSnapshot.running(
        sessionRef: sessionRef,
        origin: RowanActionCueObservationOrigin.recovered,
      );

  factory RowanActionCueScreenSharingSnapshot.fromLiveScreenSharing(
    dynamic sharing, {
    RowanActionCueObservationOrigin origin =
        RowanActionCueObservationOrigin.observed,
  }) {
    try {
      final feed = sharing.feed;
      final state = rowanActionCueScreenStateFromWire(_enumWire(feed.state));
      final rawSession = sharing.sessionId;
      final sessionRef =
          rawSession is String && rawSession.isNotEmpty ? rawSession : null;
      final error = sharing.error is String ? sharing.error as String : null;
      final busy = sharing.busy == true;
      final uncertainOpen = sharing.uncertainOpen == true;
      if (uncertainOpen && sessionRef == null) {
        return RowanActionCueScreenSharingSnapshot._(
          state: RowanActionCueScreenSharingState.starting,
          error: error,
          uncertainOpen: true,
          busy: busy,
          origin: origin,
        );
      }
      return RowanActionCueScreenSharingSnapshot._(
        state: state ?? RowanActionCueScreenSharingState.unavailable,
        sessionRef: sessionRef,
        error: error,
        uncertainOpen: uncertainOpen,
        busy: busy,
        origin: origin,
      );
    } on Object catch (error) {
      return RowanActionCueScreenSharingSnapshot.unavailable(
        error: '$error',
        origin: origin,
      );
    }
  }

  final RowanActionCueScreenSharingState state;
  final String? sessionRef, error;
  final bool uncertainOpen, busy;
  final RowanActionCueObservationOrigin origin;

  bool get hasSession => sessionRef != null && sessionRef!.isNotEmpty;

  @override
  bool operator ==(Object other) =>
      other is RowanActionCueScreenSharingSnapshot &&
      state == other.state &&
      sessionRef == other.sessionRef &&
      error == other.error &&
      uncertainOpen == other.uncertainOpen &&
      busy == other.busy &&
      origin == other.origin;

  @override
  int get hashCode =>
      Object.hash(state, sessionRef, error, uncertainOpen, busy, origin);
}

String _enumWire(dynamic value) {
  try {
    final name = value.name;
    if (name is String) return name;
  } on Object {
    // Fall back to toString below.
  }
  return '$value'.split('.').last;
}

RowanActionCueScreenSharingState? rowanActionCueScreenStateFromWire(
  String value,
) =>
    switch (value) {
      'stopped' => RowanActionCueScreenSharingState.stopped,
      'starting' => RowanActionCueScreenSharingState.starting,
      'running' => RowanActionCueScreenSharingState.running,
      'paused' => RowanActionCueScreenSharingState.paused,
      'disconnected' => RowanActionCueScreenSharingState.disconnected,
      _ => null,
    };
