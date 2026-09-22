part of 'provider_session_surface.dart';

final class _ProviderSessionStateKey {
  final String operationRef, nativeSessionId, nativeThreadId, nativeTurnId;
  final String lastProviderEventId, historyStatus, sideEffectStatus, reason;
  final ProviderSessionPhase phase;
  final bool terminal;

  const _ProviderSessionStateKey({
    required this.operationRef,
    required this.nativeSessionId,
    required this.nativeThreadId,
    required this.nativeTurnId,
    required this.lastProviderEventId,
    required this.historyStatus,
    required this.sideEffectStatus,
    required this.reason,
    required this.phase,
    required this.terminal,
  });

  factory _ProviderSessionStateKey.from(ProviderSessionState state) =>
      _ProviderSessionStateKey(
        operationRef: state.operationRef,
        nativeSessionId: state.nativeSessionId,
        nativeThreadId: state.nativeThreadId,
        nativeTurnId: state.nativeTurnId,
        lastProviderEventId: state.lastProviderEventId,
        historyStatus: state.historyStatus,
        sideEffectStatus: state.sideEffectStatus,
        reason: state.reason,
        phase: state.phase,
        terminal: state.terminal,
      );

  bool matches(ProviderSessionState state) =>
      operationRef == state.operationRef &&
      nativeSessionId == state.nativeSessionId &&
      nativeThreadId == state.nativeThreadId &&
      nativeTurnId == state.nativeTurnId &&
      lastProviderEventId == state.lastProviderEventId &&
      historyStatus == state.historyStatus &&
      sideEffectStatus == state.sideEffectStatus &&
      reason == state.reason &&
      phase == state.phase &&
      terminal == state.terminal;
}
