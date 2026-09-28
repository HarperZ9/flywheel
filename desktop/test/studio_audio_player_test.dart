import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/studio_media.dart';
import 'package:flywheel_desktop/services/studio_audio_player.dart';

import 'studio_audio_test_fixtures.dart';

void main() {
  test('loading verified audio does not autoplay and controls lifecycle',
      () async {
    final backend = FakeStudioAudioBackend();
    final controller = StudioAudioPlaybackController(backend: backend);
    final audio = StudioAudio.fromResult(studioAudioResult(studioTestWav()));

    await controller.load(audio);
    expect(controller.state.status, StudioAudioPlaybackStatus.ready);
    expect(backend.playedBytes, isEmpty);

    await controller.play();
    expect(controller.state.status, StudioAudioPlaybackStatus.playing);
    expect(backend.playedBytes.single, audio.bytes);

    await controller.pause();
    expect(controller.state.status, StudioAudioPlaybackStatus.paused);
    expect(backend.pauseCalls, 1);

    await controller.seek(const Duration(microseconds: 250));
    expect(controller.state.position, const Duration(microseconds: 250));
    expect(backend.seeks.single, const Duration(microseconds: 250));

    await controller.stop();
    expect(controller.state.status, StudioAudioPlaybackStatus.ready);
    expect(controller.state.position, Duration.zero);
    expect(backend.stopCalls, 1);
  });

  test('loading a new source stops the old audio before it can play', () async {
    final backend = FakeStudioAudioBackend();
    final controller = StudioAudioPlaybackController(backend: backend);
    final first = StudioAudio.fromResult(studioAudioResult(studioTestWav()));
    final second = StudioAudio.fromResult(studioAudioResult(
      studioTestWav(samples: const [1000, 2000, 3000, 4000]),
      seed: 59,
    ));

    await controller.load(first);
    await controller.play();
    await controller.load(second);

    expect(controller.state.audio, second);
    expect(controller.state.status, StudioAudioPlaybackStatus.ready);
    expect(backend.stopCalls, 1);
    expect(backend.playedBytes, hasLength(1));
  });

  test('dispose makes pending playback completion harmless', () async {
    final backend = FakeStudioAudioBackend();
    final controller = StudioAudioPlaybackController(backend: backend);
    final audio = StudioAudio.fromResult(studioAudioResult(studioTestWav()));

    await controller.load(audio);
    await controller.play();
    await controller.close();
    backend.complete();

    expect(backend.disposeCalls, 1);
    expect(backend.stopCalls, 1);
  });
}

class FakeStudioAudioBackend implements StudioAudioNativeBackend {
  final completions = StreamController<void>.broadcast();
  final playedBytes = <Uint8List>[];
  final seeks = <Duration>[];
  var pauseCalls = 0;
  var stopCalls = 0;
  var disposeCalls = 0;

  @override
  Stream<void> get onComplete => completions.stream;

  @override
  Future<void> playBytes(Uint8List bytes, {required String mimeType}) async {
    playedBytes.add(bytes);
  }

  @override
  Future<void> pause() async {
    pauseCalls++;
  }

  @override
  Future<void> resume() async {}

  @override
  Future<void> seek(Duration position) async {
    seeks.add(position);
  }

  @override
  Future<void> stop() async {
    stopCalls++;
  }

  @override
  Future<void> dispose() async {
    disposeCalls++;
    await completions.close();
  }

  void complete() {
    if (!completions.isClosed) completions.add(null);
  }
}
