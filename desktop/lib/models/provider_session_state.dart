part of 'provider_session_models.dart';

final class ProviderSessionEvent {
  final ProviderSessionPhase phase;
  final String rawPhase, provider, operationRef, nativeSessionId;
  final String nativeThreadId, nativeTurnId, lastProviderEventId;
  final String historyStatus, sideEffectStatus, reason;

  const ProviderSessionEvent({
    required this.phase,
    required this.rawPhase,
    this.provider = '',
    this.operationRef = '',
    this.nativeSessionId = '',
    this.nativeThreadId = '',
    this.nativeTurnId = '',
    this.lastProviderEventId = '',
    this.historyStatus = '',
    this.sideEffectStatus = '',
    this.reason = '',
  });

  factory ProviderSessionEvent.fromProgress(Map<String, dynamic> progress) {
    final raw = progress['provider_session'];
    if (raw is! Map) _bad();
    final map = Map<String, Object?>.from(raw);
    final rawPhase = _read(map, 'phase');
    return ProviderSessionEvent(
      phase: _phase(rawPhase),
      rawPhase: rawPhase,
      provider: _read(map, 'provider'),
      operationRef: _read(map, 'operation_ref', pattern: _operationRef),
      nativeSessionId: _read(map, 'native_session_id'),
      nativeThreadId: _read(map, 'native_thread_id'),
      nativeTurnId: _read(map, 'native_turn_id'),
      lastProviderEventId: _read(map, 'last_provider_event_id'),
      historyStatus: _read(map, 'history_status'),
      sideEffectStatus: _read(map, 'side_effect_status'),
      reason: _read(map, 'reason'),
    );
  }

  factory ProviderSessionEvent.fromResult(OperationResult result) {
    final session = result.result['provider_session'];
    final map = session is Map
        ? Map<String, Object?>.from(session)
        : const <String, Object?>{};
    final provider = _readResultText(map, 'provider');
    final history = _readResultText(result.result, 'history_status');
    final sideEffect = _readResultText(result.result, 'side_effect_status');
    if (provider.isEmpty ||
        !_knownHistoryStatus.contains(history) ||
        !_knownSideEffectStatus.contains(sideEffect)) {
      return ProviderSessionEvent(
        phase: ProviderSessionPhase.unknown,
        rawPhase: result.state.name,
        provider: provider,
        operationRef: result.operationRef,
        nativeSessionId: _readResultText(map, 'native_session_id'),
        nativeThreadId: _readResultText(map, 'native_thread_id'),
        nativeTurnId: _readResultText(map, 'native_turn_id'),
        lastProviderEventId: _readResultText(map, 'last_provider_event_id'),
        historyStatus: 'indeterminate',
        sideEffectStatus: 'indeterminate',
        reason: 'AGENT_NATIVE_INCOMPLETE',
      );
    }
    return ProviderSessionEvent(
      phase: ProviderSessionPhase.unknown,
      rawPhase: result.state.name,
      provider: provider,
      operationRef: result.operationRef,
      nativeSessionId: _readResultText(map, 'native_session_id'),
      nativeThreadId: _readResultText(map, 'native_thread_id'),
      nativeTurnId: _readResultText(map, 'native_turn_id'),
      lastProviderEventId: _readResultText(map, 'last_provider_event_id'),
      historyStatus: history,
      sideEffectStatus: sideEffect,
      reason: _readResultText(result.result, 'reason'),
    );
  }
}

const _knownHistoryStatus = {
  'complete',
  'indeterminate',
  'missing',
  'missing_native_history',
  'unsupported',
  'confirmed_not_applied',
};

const _knownSideEffectStatus = {
  'none',
  'input_sent',
  'unknown_after_send',
  'indeterminate',
  'write_uncertain',
  'response_write_uncertain',
  'confirmed_not_applied',
  'in_progress',
  'native_terminal_observed',
};

String _readResultText(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return '';
  return value is String && value.isNotEmpty && isSafePublicText(value)
      ? value
      : '';
}

final class ProviderSessionState {
  final String operationRef, provider, nativeSessionId, nativeThreadId;
  final String nativeTurnId, lastProviderEventId, historyStatus;
  final String sideEffectStatus, reason;
  final ProviderSessionPhase phase;
  final bool terminal;

  const ProviderSessionState({
    this.operationRef = '',
    this.provider = '',
    this.nativeSessionId = '',
    this.nativeThreadId = '',
    this.nativeTurnId = '',
    this.lastProviderEventId = '',
    this.historyStatus = '',
    this.sideEffectStatus = '',
    this.reason = '',
    this.phase = ProviderSessionPhase.idle,
    this.terminal = false,
  });

  ProviderSessionState begin(String ref) =>
      ProviderSessionState(operationRef: _safe(ref, pattern: _operationRef));

  ProviderSessionState apply(
    ProviderSessionEvent event, {
    bool terminal = false,
  }) {
    if (event.operationRef.isNotEmpty &&
        operationRef.isNotEmpty &&
        event.operationRef != operationRef) {
      return this;
    }
    return ProviderSessionState(
      operationRef:
          event.operationRef.isNotEmpty ? event.operationRef : operationRef,
      provider: event.provider.isNotEmpty ? event.provider : provider,
      nativeSessionId: event.nativeSessionId.isNotEmpty
          ? event.nativeSessionId
          : nativeSessionId,
      nativeThreadId: event.nativeThreadId.isNotEmpty
          ? event.nativeThreadId
          : nativeThreadId,
      nativeTurnId:
          event.nativeTurnId.isNotEmpty ? event.nativeTurnId : nativeTurnId,
      lastProviderEventId: event.lastProviderEventId.isNotEmpty
          ? event.lastProviderEventId
          : lastProviderEventId,
      historyStatus:
          event.historyStatus.isNotEmpty ? event.historyStatus : historyStatus,
      sideEffectStatus: event.sideEffectStatus.isNotEmpty
          ? event.sideEffectStatus
          : sideEffectStatus,
      reason: event.reason.isNotEmpty ? event.reason : reason,
      phase: event.phase,
      terminal: terminal || this.terminal,
    );
  }

  bool get needsReconcile =>
      phase == ProviderSessionPhase.closeIndeterminate ||
      reason == 'AGENT_NATIVE_INCOMPLETE' ||
      const {
        'indeterminate',
        'missing',
        'missing_native_history',
        'unsupported',
      }.contains(historyStatus) ||
      const {
        'unknown_after_send',
        'indeterminate',
        'write_uncertain',
        'response_write_uncertain',
        'in_progress',
      }.contains(sideEffectStatus);
  bool get canStop => operationRef.isNotEmpty && !terminal;
  bool get canResume => nativeThreadId.isNotEmpty || operationRef.isNotEmpty;
  bool get canSendTurn => !needsReconcile;
}

ProviderSessionPhase _phase(String value) => switch (value) {
      '' => ProviderSessionPhase.unknown,
      'dispatch_intent' => ProviderSessionPhase.dispatchIntent,
      'native_binding' => ProviderSessionPhase.nativeBinding,
      'input_sent' => ProviderSessionPhase.inputSent,
      'provider_event' => ProviderSessionPhase.providerEvent,
      'approval_replied' => ProviderSessionPhase.approvalReplied,
      'cancel_requested' => ProviderSessionPhase.cancelRequested,
      'cancel_acknowledged' => ProviderSessionPhase.cancelAcknowledged,
      'close_indeterminate' => ProviderSessionPhase.closeIndeterminate,
      _ => ProviderSessionPhase.unknown,
    };
