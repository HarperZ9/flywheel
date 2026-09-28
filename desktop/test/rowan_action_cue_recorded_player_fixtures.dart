import 'dart:async';

import 'package:audioplayers/audioplayers.dart' as audio;
import 'package:audioplayers_platform_interface/audioplayers_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_clip_model.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_recorded_player.dart';

class FakeAssetBundle extends CachingAssetBundle {
  FakeAssetBundle(this.assets);

  final Map<String, Uint8List> assets;

  @override
  Future<ByteData> load(String key) async {
    final bytes = assets[key];
    if (bytes == null) throw FlutterError('missing asset $key');
    return bytes.toByteData();
  }
}

class PendingAssetBundle extends CachingAssetBundle {
  PendingAssetBundle(this.key, this.bytes);

  final String key;
  final Uint8List bytes;
  final started = Completer<void>();
  final release = Completer<void>();

  @override
  Future<ByteData> load(String key) async {
    if (key != this.key) throw FlutterError('missing asset $key');
    started.complete();
    await release.future;
    return bytes.toByteData();
  }
}

extension TestBytes on Uint8List {
  ByteData toByteData() {
    final data = ByteData(length);
    for (var index = 0; index < length; index++) {
      data.setUint8(index, this[index]);
    }
    return data;
  }
}

class FakeNativeAudioBackend implements RowanActionCueAudioBackend {
  final played = <String>[];
  final completed = StreamController<void>.broadcast();
  var stopCalls = 0;
  var disposeCalls = 0;

  @override
  Stream<void> get onComplete => completed.stream;

  @override
  Future<void> playAsset(String assetKey, {required String mimeType}) async {
    played.add('$assetKey|$mimeType');
  }

  @override
  Future<void> stop() async {
    stopCalls++;
  }

  @override
  Future<void> dispose() async {
    disposeCalls++;
    await completed.close();
  }
}

class PendingNativeAudioBackend implements RowanActionCueAudioBackend {
  final played = <String>[];
  final stops = <String>[];
  final completed = StreamController<void>.broadcast();
  final firstPlayStarted = Completer<void>();
  final releaseFirstPlay = Completer<void>();

  @override
  Stream<void> get onComplete => completed.stream;

  @override
  Future<void> playAsset(String assetKey, {required String mimeType}) async {
    played.add('$assetKey|$mimeType');
    if (!firstPlayStarted.isCompleted) {
      firstPlayStarted.complete();
      await releaseFirstPlay.future;
    }
  }

  @override
  Future<void> stop() async {
    stops.add('stop');
  }

  @override
  Future<void> dispose() async {
    await completed.close();
  }
}

class FakeAudioCache extends audio.AudioCache {
  FakeAudioCache() : super(prefix: 'assets/', cacheId: 'rowan-test-cache');

  @override
  Future<String> loadPath(String fileName) async =>
      'file:///tmp/rowan-test-cache/$fileName';
}

class FakeGlobalAudioPlatform extends GlobalAudioplayersPlatformInterface {
  var initCalls = 0;

  @override
  Future<void> init() async {
    initCalls++;
  }

  @override
  Stream<GlobalAudioEvent> getGlobalEventStream() =>
      const Stream<GlobalAudioEvent>.empty();

  @override
  Future<void> setGlobalAudioContext(AudioContext ctx) async {}

  @override
  Future<void> emitGlobalLog(String message) async {}

  @override
  Future<void> emitGlobalError(String code, String message) async {}
}

class FakeAudioplayersPlatform extends AudioplayersPlatformInterface {
  final created = <String>[];
  final disposed = <String>[];
  final stopped = <String>[];
  final resumed = <String>[];
  final sources = <Map<String, Object?>>[];
  final streams = <String, StreamController<AudioEvent>>{};

  void complete(String playerId) {
    streams[playerId]!.add(
      const AudioEvent(eventType: AudioEventType.complete),
    );
  }

  @override
  Future<void> create(String playerId) async {
    created.add(playerId);
    streams[playerId] = StreamController<AudioEvent>.broadcast();
  }

  @override
  Future<void> dispose(String playerId) async {
    disposed.add(playerId);
    await streams.remove(playerId)?.close();
  }

  @override
  Stream<AudioEvent> getEventStream(String playerId) =>
      streams[playerId]!.stream;

  @override
  Future<void> setSourceUrl(
    String playerId,
    String url, {
    bool? isLocal,
    String? mimeType,
  }) async {
    sources.add({
      'playerId': playerId,
      'url': url,
      'isLocal': isLocal,
      'mimeType': mimeType,
    });
    streams[playerId]!.add(
      const AudioEvent(
        eventType: AudioEventType.prepared,
        isPrepared: true,
      ),
    );
  }

  @override
  Future<void> resume(String playerId) async {
    resumed.add(playerId);
  }

  @override
  Future<void> stop(String playerId) async {
    stopped.add(playerId);
  }

  @override
  Future<void> pause(String playerId) async {}

  @override
  Future<void> release(String playerId) async {}

  @override
  Future<void> seek(String playerId, Duration position) async {}

  @override
  Future<void> setBalance(String playerId, double balance) async {}

  @override
  Future<void> setVolume(String playerId, double volume) async {}

  @override
  Future<void> setReleaseMode(String playerId, ReleaseMode mode) async {}

  @override
  Future<void> setPlaybackRate(String playerId, double rate) async {}

  @override
  Future<void> setSourceBytes(
    String playerId,
    Uint8List bytes, {
    String? mimeType,
  }) async {}

  @override
  Future<void> setAudioContext(String playerId, AudioContext context) async {}

  @override
  Future<void> setPlayerMode(String playerId, PlayerMode mode) async {}

  @override
  Future<int?> getDuration(String playerId) async => null;

  @override
  Future<int?> getCurrentPosition(String playerId) async => null;

  @override
  Future<void> emitLog(String playerId, String message) async {}

  @override
  Future<void> emitError(String playerId, String code, String message) async {}
}

RowanActionClip recordedClip({required String audioSha256}) => RowanActionClip(
      eventId: 'operation.working',
      clipId: 'test:operation.working:v1',
      variantId: 'v1',
      assetKey: 'rowan/action-cues/test/working.wav',
      caption: 'Working.',
      category: 'operation',
      context: 'operation-state',
      prerequisite: 'Live operation progress observed.',
      trigger: 'Live operation progress observed.',
      textSha256:
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      audioSha256: audioSha256,
      durationSeconds: 1,
      recommendedCooldownSeconds: 3,
      manifestSha256:
          'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      sourcePack: 'test-pack',
      generation: 'test',
      provenanceBasis: 'test-fixture',
    );
