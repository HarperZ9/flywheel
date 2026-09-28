import 'dart:async';

import 'package:audioplayers/audioplayers.dart' as audio;
import 'package:flutter/services.dart';

import 'rowan_action_cue_clip_model.dart';
import 'rowan_action_cue_hash.dart';
import 'rowan_action_cue_player.dart';

final _safeAssetKey = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_./-]*[.]wav$');

class RowanActionCuePlaybackException implements Exception {
  RowanActionCuePlaybackException(this.message, {this.assetKey, this.cause});

  final String message;
  final String? assetKey;
  final Object? cause;

  @override
  String toString() {
    final target = assetKey == null ? '' : ' ($assetKey)';
    final source = cause == null ? '' : ': $cause';
    return 'RowanActionCuePlaybackException: $message$target$source';
  }
}

abstract interface class RowanActionCueAudioBackend {
  Stream<void> get onComplete;
  Future<void> playAsset(String assetKey, {required String mimeType});
  Future<void> stop();
  Future<void> dispose();
}

class AudioplayersRowanActionCueBackend implements RowanActionCueAudioBackend {
  AudioplayersRowanActionCueBackend({audio.AudioPlayer? player})
      : _player = player ?? audio.AudioPlayer();

  final audio.AudioPlayer _player;

  @override
  Stream<void> get onComplete => _player.onPlayerComplete;

  @override
  Future<void> playAsset(String assetKey, {required String mimeType}) =>
      _player.play(audio.AssetSource(assetKey, mimeType: mimeType));

  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> dispose() => _player.dispose();
}

class RowanRecordedAssetCuePlayer implements RowanActionCuePlayer {
  RowanRecordedAssetCuePlayer({
    AssetBundle? assetBundle,
    RowanActionCueAudioBackend? backend,
    this.onCaption,
    this.onComplete,
    this.onStopped,
  })  : _assetBundle = assetBundle ?? rootBundle,
        _backend = backend ?? AudioplayersRowanActionCueBackend() {
    _completeSubscription =
        _backend.onComplete.listen((_) => onComplete?.call());
  }

  final AssetBundle _assetBundle;
  final RowanActionCueAudioBackend _backend;
  final void Function(RowanActionCuePlayback playback)? onCaption;
  final void Function()? onComplete;
  final void Function()? onStopped;
  late final StreamSubscription<void> _completeSubscription;
  Future<void> _operation = Future<void>.value();
  var _generation = 0;
  bool _nativeStarted = false;

  @override
  Stream<void> get completions => _backend.onComplete;

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    final generation = ++_generation;
    return _serialize(() => _playLocked(playback, generation));
  }

  Future<void> _playLocked(
    RowanActionCuePlayback playback,
    int generation,
  ) async {
    if (generation != _generation) {
      throw RowanActionCuePlaybackException('recorded cue playback superseded');
    }
    if (playback.source != RowanActionCueAudioSource.recordedClip) {
      throw RowanActionCuePlaybackException(
          'local synthesis player not mounted');
    }
    final clip = playback.recordedClip;
    if (clip == null) {
      throw RowanActionCuePlaybackException('recorded clip missing');
    }
    await _verifyClipAsset(clip);
    if (generation != _generation) {
      throw RowanActionCuePlaybackException('recorded cue playback superseded');
    }
    if (_nativeStarted) {
      await _stopNativeLocked('recorded cue replacement stop failed');
    }
    if (generation != _generation) {
      throw RowanActionCuePlaybackException('recorded cue playback superseded');
    }
    await _backend.playAsset(clip.assetKey, mimeType: 'audio/wav');
    _nativeStarted = true;
    if (generation != _generation) {
      throw RowanActionCuePlaybackException('recorded cue playback superseded');
    }
    onCaption?.call(playback);
  }

  @override
  Future<void> stop() async {
    _generation++;
    return _serialize(() => _stopNativeLocked('recorded cue stop failed'));
  }

  Future<void> dispose() async {
    _generation++;
    await _serialize(() async {
      await _completeSubscription.cancel();
      await _backend.dispose();
      _nativeStarted = false;
    });
  }

  Future<T> _serialize<T>(Future<T> Function() action) {
    final run = _operation.then(
      (_) => action(),
      onError: (_) => action(),
    );
    _operation = run.then<void>((_) {}, onError: (_) {});
    return run;
  }

  Future<void> _stopNativeLocked(String failureMessage) async {
    try {
      await _backend.stop();
      _nativeStarted = false;
      onStopped?.call();
    } catch (error) {
      throw RowanActionCuePlaybackException(failureMessage, cause: error);
    }
  }

  Future<void> _verifyClipAsset(RowanActionClip clip) async {
    if (!_isSafeAssetKey(clip.assetKey)) {
      throw RowanActionCuePlaybackException(
        'unsafe recorded cue asset key',
        assetKey: clip.assetKey,
      );
    }
    final bytes = await _assetBundle.load('assets/${clip.assetKey}');
    final digest = rowanActionCueBytesSha256(_asBytes(bytes));
    if (digest != clip.audioSha256) {
      throw RowanActionCuePlaybackException(
        'recorded cue asset hash mismatch',
        assetKey: clip.assetKey,
      );
    }
  }
}

bool _isSafeAssetKey(String assetKey) {
  if (!_safeAssetKey.hasMatch(assetKey)) return false;
  if (assetKey.contains('://') || assetKey.contains('\\')) return false;
  final parts = assetKey.split('/');
  return parts.every((part) => part.isNotEmpty && part != '.' && part != '..');
}

Uint8List _asBytes(ByteData data) => data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
