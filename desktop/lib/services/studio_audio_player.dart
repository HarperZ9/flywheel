import 'dart:async';

import 'package:audioplayers/audioplayers.dart' as audio;
import 'package:flutter/foundation.dart';

import '../models/studio_media.dart';

enum StudioAudioPlaybackStatus {
  empty,
  ready,
  playing,
  paused,
  completed,
  error
}

class StudioAudioPlaybackState {
  const StudioAudioPlaybackState({
    this.audio,
    this.status = StudioAudioPlaybackStatus.empty,
    this.position = Duration.zero,
    this.error,
  });

  final StudioAudio? audio;
  final StudioAudioPlaybackStatus status;
  final Duration position;
  final String? error;

  bool get hasAudio => audio != null;
  bool get isPlaying => status == StudioAudioPlaybackStatus.playing;
  Duration get duration => audio?.duration ?? Duration.zero;
}

abstract interface class StudioAudioPlayback implements Listenable {
  StudioAudioPlaybackState get state;
  Future<void> load(StudioAudio audio);
  Future<void> clear();
  Future<void> play();
  Future<void> pause();
  Future<void> stop();
  Future<void> seek(Duration position);
  Future<void> close();
}

abstract interface class StudioAudioNativeBackend {
  Stream<void> get onComplete;
  Future<void> playBytes(Uint8List bytes, {required String mimeType});
  Future<void> resume();
  Future<void> pause();
  Future<void> stop();
  Future<void> seek(Duration position);
  Future<void> dispose();
}

class AudioplayersStudioAudioBackend implements StudioAudioNativeBackend {
  AudioplayersStudioAudioBackend({audio.AudioPlayer? player})
      : _player = player ?? audio.AudioPlayer();

  final audio.AudioPlayer _player;

  @override
  Stream<void> get onComplete => _player.onPlayerComplete;

  @override
  Future<void> playBytes(Uint8List bytes, {required String mimeType}) =>
      _player.play(audio.BytesSource(bytes, mimeType: mimeType));

  @override
  Future<void> resume() => _player.resume();

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> seek(Duration position) => _player.seek(position);

  @override
  Future<void> dispose() => _player.dispose();
}

class StudioAudioPlaybackController implements StudioAudioPlayback {
  StudioAudioPlaybackController({StudioAudioNativeBackend? backend})
      : _backend = backend ?? AudioplayersStudioAudioBackend() {
    _completeSubscription = _backend.onComplete.listen((_) {
      if (_closed || _state.status != StudioAudioPlaybackStatus.playing) return;
      final audio = _state.audio;
      if (audio == null) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: StudioAudioPlaybackStatus.completed,
        position: audio.duration,
      ));
    });
  }

  final StudioAudioNativeBackend _backend;
  final _StudioAudioNotifier _notifier = _StudioAudioNotifier();
  late final StreamSubscription<void> _completeSubscription;
  Future<void> _operation = Future<void>.value();
  StudioAudioPlaybackState _state = const StudioAudioPlaybackState();
  var _generation = 0;
  var _nativeStarted = false;
  var _closed = false;

  @override
  StudioAudioPlaybackState get state => _state;

  @override
  void addListener(VoidCallback listener) => _notifier.addListener(listener);

  @override
  void removeListener(VoidCallback listener) =>
      _notifier.removeListener(listener);

  @override
  Future<void> load(StudioAudio audio) {
    final generation = ++_generation;
    return _serialize(() async {
      if (_closed || generation != _generation) return;
      if (_nativeStarted) await _backend.stop();
      _nativeStarted = false;
      if (_closed || generation != _generation) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: StudioAudioPlaybackStatus.ready,
      ));
    });
  }

  @override
  Future<void> clear() {
    final generation = ++_generation;
    return _serialize(() async {
      if (_closed || generation != _generation) return;
      if (_nativeStarted) await _backend.stop();
      _nativeStarted = false;
      if (_closed || generation != _generation) return;
      _set(const StudioAudioPlaybackState());
    });
  }

  @override
  Future<void> play() {
    final generation = ++_generation;
    return _serialize(() async {
      final audio = _state.audio;
      if (_closed || generation != _generation || audio == null) return;
      if (_state.status == StudioAudioPlaybackStatus.paused) {
        await _backend.resume();
      } else {
        await _backend.playBytes(audio.bytes, mimeType: 'audio/wav');
      }
      _nativeStarted = true;
      if (_closed || generation != _generation) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: StudioAudioPlaybackStatus.playing,
        position: _state.status == StudioAudioPlaybackStatus.paused
            ? _state.position
            : Duration.zero,
      ));
    });
  }

  @override
  Future<void> pause() {
    final generation = ++_generation;
    return _serialize(() async {
      final audio = _state.audio;
      if (_closed ||
          generation != _generation ||
          audio == null ||
          _state.status != StudioAudioPlaybackStatus.playing) {
        return;
      }
      await _backend.pause();
      if (_closed || generation != _generation) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: StudioAudioPlaybackStatus.paused,
        position: _state.position,
      ));
    });
  }

  @override
  Future<void> stop() {
    final generation = ++_generation;
    return _serialize(() async {
      final audio = _state.audio;
      if (_closed || generation != _generation || audio == null) return;
      if (_nativeStarted) await _backend.stop();
      _nativeStarted = false;
      if (_closed || generation != _generation) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: StudioAudioPlaybackStatus.ready,
      ));
    });
  }

  @override
  Future<void> seek(Duration position) {
    final generation = _generation;
    return _serialize(() async {
      final audio = _state.audio;
      if (_closed || generation != _generation || audio == null) return;
      final clamped = _clamp(position, audio.duration);
      await _backend.seek(clamped);
      if (_closed || generation != _generation) return;
      _set(StudioAudioPlaybackState(
        audio: audio,
        status: _state.status,
        position: clamped,
        error: _state.error,
      ));
    });
  }

  @override
  Future<void> close() {
    if (_closed) return _operation;
    _closed = true;
    _generation++;
    return _serialize(() async {
      await _completeSubscription.cancel();
      if (_nativeStarted) await _backend.stop();
      await _backend.dispose();
      _nativeStarted = false;
      _notifier.dispose();
    });
  }

  Future<T> _serialize<T>(Future<T> Function() action) {
    final run = _operation.then((_) => action(), onError: (_) => action());
    _operation = run.then<void>((_) {}, onError: (_) {});
    return run;
  }

  void _set(StudioAudioPlaybackState state) {
    _state = state;
    _notifier.emit();
  }
}

class _StudioAudioNotifier extends ChangeNotifier {
  void emit() => notifyListeners();
}

Duration _clamp(Duration value, Duration max) {
  if (value < Duration.zero) return Duration.zero;
  if (value > max) return max;
  return value;
}
