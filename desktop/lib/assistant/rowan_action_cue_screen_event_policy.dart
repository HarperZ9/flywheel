import 'rowan_action_cue_complete_ids.dart';
import 'rowan_action_cue_event_binding_screen.dart';
import 'rowan_action_cue_hash.dart';
import 'rowan_action_cue_models.dart';

final class RowanActionCueScreenEventPolicy {
  final _localSessions = <String>{};
  final _recoveredSessions = <String>{};
  final _receiptCuedSessions = <String>{};

  List<RowanActionCueEvent> events(
    RowanActionCueScreenSharingSnapshot? prior,
    RowanActionCueScreenSharingSnapshot? current,
  ) {
    if (prior == null || current == null || prior == current) return const [];
    final sessionRef = current.sessionRef ?? prior.sessionRef;
    _rememberSessionOrigin(current);
    if (_isRecoveredSession(sessionRef)) {
      _forgetEndedSession(current, sessionRef);
      return const [];
    }
    final lifecycle = _lifecycleEvent(prior, current, sessionRef);
    final receipt = _providerReceiptEvent(current);
    _forgetEndedSession(current, sessionRef);
    final events = <RowanActionCueEvent>[
      if (lifecycle != null) lifecycle,
      if (receipt != null) receipt,
    ];
    if (receipt != null && current.sessionRef != null) {
      _receiptCuedSessions.add(current.sessionRef!);
    }
    return events;
  }

  void _rememberSessionOrigin(RowanActionCueScreenSharingSnapshot current) {
    final sessionRef = current.sessionRef;
    if (sessionRef == null) return;
    switch (current.origin) {
      case RowanActionCueObservationOrigin.localStart:
        _localSessions.add(sessionRef);
      case RowanActionCueObservationOrigin.recovered:
        _recoveredSessions.add(sessionRef);
      case RowanActionCueObservationOrigin.observed:
        break;
    }
  }

  bool _isRecoveredSession(String? sessionRef) =>
      sessionRef != null && _recoveredSessions.contains(sessionRef);

  void _forgetEndedSession(
    RowanActionCueScreenSharingSnapshot current,
    String? sessionRef,
  ) {
    if (current.state != RowanActionCueScreenSharingState.stopped ||
        sessionRef == null) {
      return;
    }
    _localSessions.remove(sessionRef);
    _recoveredSessions.remove(sessionRef);
    _receiptCuedSessions.remove(sessionRef);
  }

  RowanActionCueEvent? _lifecycleEvent(
    RowanActionCueScreenSharingSnapshot prior,
    RowanActionCueScreenSharingSnapshot current,
    String? sessionRef,
  ) {
    final priorState = prior.state;
    final nextState = current.state;
    if (nextState == RowanActionCueScreenSharingState.paused) return null;
    final sessionChanged =
        current.sessionRef != null && prior.sessionRef != current.sessionRef;
    final localSession =
        sessionRef != null && _localSessions.contains(sessionRef);
    final kind = switch (nextState) {
      RowanActionCueScreenSharingState.running
          when priorState == RowanActionCueScreenSharingState.disconnected ||
              priorState == RowanActionCueScreenSharingState.unavailable =>
        RowanActionCueKind.connectionRestored,
      RowanActionCueScreenSharingState.running
          when current.origin == RowanActionCueObservationOrigin.localStart ||
              prior.origin == RowanActionCueObservationOrigin.localStart &&
                  (sessionChanged ||
                      priorState == RowanActionCueScreenSharingState.stopped ||
                      priorState ==
                          RowanActionCueScreenSharingState.starting) =>
        RowanCompleteActionCueEvents.privacyLiveScreenOn,
      RowanActionCueScreenSharingState.stopped
          when localSession &&
              (prior.hasSession ||
                  priorState == RowanActionCueScreenSharingState.running ||
                  priorState == RowanActionCueScreenSharingState.paused ||
                  priorState ==
                      RowanActionCueScreenSharingState.disconnected) =>
        RowanCompleteActionCueEvents.privacyLiveScreenOff,
      RowanActionCueScreenSharingState.disconnected when prior.hasSession =>
        RowanActionCueKind.connectionReconnecting,
      RowanActionCueScreenSharingState.unavailable when prior.hasSession =>
        RowanActionCueKind.connectionReconnecting,
      _ => null,
    };
    return kind == null
        ? null
        : RowanActionCueEvent.fromStableEvent(
            kind: kind,
            eventRef: _screenEventRef(kind, current, sessionRef),
          );
  }

  RowanActionCueEvent? _providerReceiptEvent(
    RowanActionCueScreenSharingSnapshot current,
  ) {
    final sessionRef = current.sessionRef;
    if (current.state != RowanActionCueScreenSharingState.running ||
        sessionRef == null ||
        current.providerReceiptRef == null ||
        !_localSessions.contains(sessionRef)) {
      return null;
    }
    if (_receiptCuedSessions.contains(sessionRef)) {
      return null;
    }
    return RowanActionCueEvent.fromStableEvent(
      kind: RowanCompleteActionCueEvents.modelProviderReceipt,
      eventRef: _screenReceiptEventRef(current),
    );
  }

  String _screenEventRef(
    RowanActionCueKind kind,
    RowanActionCueScreenSharingSnapshot snapshot,
    String? sessionRef,
  ) {
    final digest = rowanActionCueSha256({
      'kind': kind.wire,
      'session_ref': sessionRef ?? snapshot.sessionRef,
      'state': snapshot.state.name,
      'uncertain_open': snapshot.uncertainOpen,
      'origin': snapshot.origin.name,
    });
    return 'screen_${digest.substring(0, 32)}';
  }

  String _screenReceiptEventRef(RowanActionCueScreenSharingSnapshot snapshot) {
    final digest = rowanActionCueSha256({
      'kind': RowanCompleteActionCueEvents.modelProviderReceipt.wire,
      'session_ref': snapshot.sessionRef,
    });
    return 'screen_receipt_${digest.substring(0, 32)}';
  }
}
