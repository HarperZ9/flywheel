import 'rowan_action_cue_clip_model.dart';

enum RowanActionCueOutcome { played, replayed, suppressed }

enum RowanActionCueReason {
  none,
  optInDisabled,
  muted,
  duplicateEvent,
  cooldown,
  historicEvent,
  noClip,
  playbackCancelled,
  playbackFailed,
  cancellationFailed,
}

enum RowanActionCueCancellationStatus {
  idle,
  stopping,
  stopped,
  failed,
}

class RowanActionCueCancellationState {
  const RowanActionCueCancellationState({
    required this.status,
    this.message,
  });

  const RowanActionCueCancellationState.idle()
      : status = RowanActionCueCancellationStatus.idle,
        message = null;

  const RowanActionCueCancellationState.stopping()
      : status = RowanActionCueCancellationStatus.stopping,
        message = 'Audio cancellation requested; playback state unknown.';

  const RowanActionCueCancellationState.stopped()
      : status = RowanActionCueCancellationStatus.stopped,
        message = 'Audio cancellation completed.';

  factory RowanActionCueCancellationState.failed(Object error) =>
      RowanActionCueCancellationState(
        status: RowanActionCueCancellationStatus.failed,
        message: 'Audio cancellation failed; playback state unknown: $error',
      );

  final RowanActionCueCancellationStatus status;
  final String? message;
}

class RowanActionCueSettings {
  const RowanActionCueSettings({
    this.enabled = false,
    this.muted = false,
    this.cooldown = const Duration(seconds: 3),
  });

  final bool enabled;
  final bool muted;
  final Duration cooldown;

  RowanActionCueSettings copyWith({
    bool? enabled,
    bool? muted,
    Duration? cooldown,
  }) =>
      RowanActionCueSettings(
        enabled: enabled ?? this.enabled,
        muted: muted ?? this.muted,
        cooldown: cooldown ?? this.cooldown,
      );
}

class RowanActionCueDecision {
  const RowanActionCueDecision({
    required this.outcome,
    required this.reason,
    this.caption,
    this.telemetry,
  });

  final RowanActionCueOutcome outcome;
  final RowanActionCueReason reason;
  final String? caption;
  final RowanActionCueTelemetry? telemetry;
}
