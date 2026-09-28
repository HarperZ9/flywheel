import 'dart:async';

import 'package:flutter/foundation.dart';

export 'rowan_action_cue_controller_models.dart';

import 'rowan_action_cue_caption.dart';
import 'rowan_action_cue_clip_model.dart';
import 'rowan_action_cue_clips.dart';
import 'rowan_action_cue_controller_models.dart';
import 'rowan_action_cue_models.dart';
import 'rowan_action_cue_player.dart';

class RowanActionCueController {
  RowanActionCueController({
    required this.player,
    RowanActionClipRegistry? registry,
    RowanActionCueSettings settings = const RowanActionCueSettings(),
    ValueNotifier<RowanActionCueCaptionState?>? captions,
    ValueNotifier<RowanActionCueCancellationState>? cancellation,
    DateTime Function()? now,
    this.stopPlayerOnDispose = true,
  })  : _registry = registry ?? RowanActionClipRegistry.cartesiaActionPack(),
        _settings = settings,
        captions = captions ?? ValueNotifier<RowanActionCueCaptionState?>(null),
        cancellation = cancellation ??
            ValueNotifier<RowanActionCueCancellationState>(
              const RowanActionCueCancellationState.idle(),
            ),
        _now = now ?? DateTime.now {
    assert(!settings.enabled || settings.cooldown >= Duration.zero);
    _completeSubscription = player.completions.listen((_) {
      _playing = false;
    });
  }

  static const maxRememberedCueKeys = 200;

  final RowanActionCuePlayer player;
  final ValueNotifier<RowanActionCueCaptionState?> captions;
  final ValueNotifier<RowanActionCueCancellationState> cancellation;
  final bool stopPlayerOnDispose;
  final RowanActionClipRegistry _registry;
  final DateTime Function() _now;
  RowanActionCueSettings _settings;
  final _playedEvents = <String>{};
  final _pendingEvents = <String>{};
  final _playedEventOrder = <String>[];
  final _lastCueAt = <String, DateTime>{};
  final _lastCueOrder = <String>[];
  final _telemetry = <RowanActionCueTelemetry>[];
  late final StreamSubscription<void> _completeSubscription;
  var _generation = 0;
  bool _playing = false;
  bool _playPending = false;
  bool _disposed = false;

  RowanActionCueSettings get settings => _settings;
  List<RowanActionCueTelemetry> get telemetry => List.unmodifiable(_telemetry);

  void setEnabled(bool value) {
    if (_disposed) return;
    _settings = _settings.copyWith(enabled: value);
    if (!value) _cancelPlayback();
  }

  void setMuted(bool value) {
    if (_disposed) return;
    _settings = _settings.copyWith(muted: value);
    if (value) _cancelPlayback();
  }

  Future<void> stop() async {
    if (_disposed) return;
    final generation = ++_generation;
    _pendingEvents.clear();
    _playPending = false;
    _playing = false;
    cancellation.value = const RowanActionCueCancellationState.stopping();
    final stopped = await _stopPlayerForCancellation(generation);
    if (!stopped) {
      throw StateError(
        cancellation.value.message ??
            'Audio cancellation failed; playback state unknown.',
      );
    }
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    final hadPlayback = _playPending || _playing || _pendingEvents.isNotEmpty;
    final generation = ++_generation;
    _pendingEvents.clear();
    _playPending = false;
    _playing = false;
    await _completeSubscription.cancel();
    if (stopPlayerOnDispose && hadPlayback) {
      await _stopPlayerForCancellation(generation, updateNotifier: false);
    }
  }

  Future<RowanActionCueDecision> handle(RowanActionCueEvent event) =>
      _attempt(event, replay: false);

  Future<RowanActionCueDecision> replay(RowanActionCueEvent event) =>
      _attempt(event, replay: true);

  Future<RowanActionCueDecision> _attempt(
    RowanActionCueEvent event, {
    required bool replay,
  }) async {
    if (_disposed) {
      return _suppressed(RowanActionCueReason.playbackCancelled);
    }
    if (!_settings.enabled) {
      return _suppressed(RowanActionCueReason.optInDisabled);
    }
    if (_settings.muted) {
      return _suppressed(RowanActionCueReason.muted);
    }
    if (!replay && event.recovered) {
      return _suppressed(RowanActionCueReason.historicEvent);
    }
    final selection = _registry.selectClip(event.kind, event.eventRef);
    if (selection == null) {
      return _suppressed(RowanActionCueReason.noClip);
    }
    final clip = selection.clip;
    final now = _now();
    final last = _lastCueAt[event.cooldownKey];
    if (!replay &&
        (_playedEvents.contains(event.dedupeKey) ||
            _pendingEvents.contains(event.dedupeKey))) {
      return _suppressed(RowanActionCueReason.duplicateEvent);
    }
    final cooldown = _cooldownFor(clip);
    if (!replay && last != null && now.difference(last) < cooldown) {
      return _suppressed(RowanActionCueReason.cooldown);
    }
    final reserved = !replay;
    if (reserved) _pendingEvents.add(event.dedupeKey);
    if (_playing || _playPending) {
      final stopped = await _stopForReplacement();
      if (!stopped) {
        if (reserved) _pendingEvents.remove(event.dedupeKey);
        return _suppressed(RowanActionCueReason.cancellationFailed);
      }
    }
    final generation = _generation;
    _playPending = true;
    final caption =
        '${replay ? 'Recorded replay' : 'Recorded cue'}: ${clip.caption}';
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: caption,
      selectionSha256: selection.selectionSha256,
      recordedReplay: replay,
    );
    try {
      await player.play(playback);
    } catch (_) {
      if (reserved) _pendingEvents.remove(event.dedupeKey);
      if (generation == _generation) _playPending = false;
      if (generation != _generation ||
          _disposed ||
          !_settings.enabled ||
          _settings.muted) {
        return _suppressed(RowanActionCueReason.playbackCancelled);
      }
      return _suppressed(RowanActionCueReason.playbackFailed);
    }
    if (reserved) _pendingEvents.remove(event.dedupeKey);
    if (generation != _generation ||
        _disposed ||
        !_settings.enabled ||
        _settings.muted) {
      if (generation == _generation) _playPending = false;
      return _suppressed(RowanActionCueReason.playbackCancelled);
    }
    _playing = true;
    _playPending = false;
    if (reserved) _rememberPlayed(event.dedupeKey);
    _rememberCooldown(event.cooldownKey, now);
    final telemetry = RowanActionCueTelemetry(
      kind: event.kind,
      eventRef: event.eventRef,
      eventSha256: event.eventSha256,
      operationRef: event.operationRef,
      clipId: clip.clipId,
      clipSha256: clip.clipSha256,
      variantId: clip.variantId,
      clipSelectionSha256: selection.selectionSha256,
      textSha256: playback.textSha256,
      audioSha256: playback.audioSha256,
      captionSha256: playback.captionSha256,
      playbackProvenanceSha256: playback.provenanceSha256,
      recordedReplay: replay,
      provesTaskCorrectness: false,
    );
    _rememberTelemetry(telemetry);
    captions.value = RowanActionCueCaptionState.fromPlayback(
      playback,
      operationRef: event.operationRef,
      eventRef: event.eventRef,
    );
    return RowanActionCueDecision(
      outcome: replay
          ? RowanActionCueOutcome.replayed
          : RowanActionCueOutcome.played,
      reason: RowanActionCueReason.none,
      caption: caption,
      telemetry: telemetry,
    );
  }

  Duration _cooldownFor(RowanActionClip clip) {
    final recommended = Duration(
      milliseconds: (clip.recommendedCooldownSeconds * 1000).round(),
    );
    return recommended > _settings.cooldown ? recommended : _settings.cooldown;
  }

  void _cancelPlayback() {
    if (_disposed) return;
    final generation = ++_generation;
    _pendingEvents.clear();
    _playPending = false;
    _playing = false;
    cancellation.value = const RowanActionCueCancellationState.stopping();
    unawaited(_stopPlayerForCancellation(generation));
  }

  Future<bool> _stopForReplacement() async {
    final generation = ++_generation;
    _playPending = false;
    _playing = false;
    cancellation.value = const RowanActionCueCancellationState.stopping();
    return _stopPlayerForCancellation(generation);
  }

  Future<bool> _stopPlayerForCancellation(
    int generation, {
    bool updateNotifier = true,
  }) async {
    try {
      await player.stop();
      if (!_disposed && updateNotifier && generation == _generation) {
        cancellation.value = const RowanActionCueCancellationState.stopped();
      }
      return true;
    } catch (error) {
      if (!_disposed && updateNotifier && generation == _generation) {
        cancellation.value = RowanActionCueCancellationState.failed(error);
      }
      return false;
    }
  }

  void _rememberPlayed(String key) {
    if (!_playedEvents.add(key)) return;
    _playedEventOrder.add(key);
    if (_playedEventOrder.length > maxRememberedCueKeys) {
      _playedEvents.remove(_playedEventOrder.removeAt(0));
    }
  }

  void _rememberCooldown(String key, DateTime value) {
    if (!_lastCueAt.containsKey(key)) _lastCueOrder.add(key);
    _lastCueAt[key] = value;
    if (_lastCueOrder.length > maxRememberedCueKeys) {
      _lastCueAt.remove(_lastCueOrder.removeAt(0));
    }
  }

  void _rememberTelemetry(RowanActionCueTelemetry telemetry) {
    if (_telemetry.length == maxRememberedCueKeys) _telemetry.removeAt(0);
    _telemetry.add(telemetry);
  }

  RowanActionCueDecision _suppressed(RowanActionCueReason reason) =>
      RowanActionCueDecision(
          outcome: RowanActionCueOutcome.suppressed, reason: reason);
}
