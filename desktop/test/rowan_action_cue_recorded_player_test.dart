import 'package:audioplayers/audioplayers.dart' as audio;
import 'package:audioplayers_platform_interface/audioplayers_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_clips.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_hash.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_models.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_recorded_player.dart';

import 'rowan_action_cue_recorded_player_fixtures.dart';

void main() {
  test('audioplayers backend routes asset playback through native platform',
      () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final globalPlatform = FakeGlobalAudioPlatform();
    final platform = FakeAudioplayersPlatform();
    GlobalAudioplayersPlatformInterface.instance = globalPlatform;
    AudioplayersPlatformInterface.instance = platform;
    final player = audio.AudioPlayer(playerId: 'rowan-test-player')
      ..audioCache = FakeAudioCache();
    final backend = AudioplayersRowanActionCueBackend(player: player);
    final completed = <String>[];
    final completionSubscription =
        backend.onComplete.listen((_) => completed.add('complete'));

    await backend.playAsset(
      'rowan/action-cues/cartesia-rowan-complete-pack/audio/cartesia-rowan-action-pack-working.wav',
      mimeType: 'audio/wav',
    );
    platform.complete('rowan-test-player');
    await Future<void>.delayed(Duration.zero);
    await backend.stop();
    expect(platform.stopped, ['rowan-test-player']);
    await backend.dispose();
    await completionSubscription.cancel();

    expect(globalPlatform.initCalls, 1);
    expect(platform.created, ['rowan-test-player']);
    expect(platform.sources.single, {
      'playerId': 'rowan-test-player',
      'url':
          'file:///tmp/rowan-test-cache/rowan/action-cues/cartesia-rowan-complete-pack/audio/cartesia-rowan-action-pack-working.wav',
      'isLocal': true,
      'mimeType': 'audio/wav',
    });
    expect(platform.resumed, ['rowan-test-player']);
    expect(completed, ['complete']);
    expect(platform.stopped, contains('rowan-test-player'));
    expect(platform.disposed, ['rowan-test-player']);
  });

  test('recorded asset player verifies bytes before native playback', () async {
    final bytes = Uint8List.fromList([1, 2, 3, 4]);
    final clip = recordedClip(audioSha256: rowanActionCueBytesSha256(bytes));
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: 'Recorded cue: Working.',
      selectionSha256:
          'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      recordedReplay: false,
    );
    final backend = FakeNativeAudioBackend();
    final captions = <RowanActionCuePlayback>[];
    final player = RowanRecordedAssetCuePlayer(
      assetBundle: FakeAssetBundle({'assets/${clip.assetKey}': bytes}),
      backend: backend,
      onCaption: captions.add,
    );

    await player.play(playback);

    expect(backend.played.single, '${clip.assetKey}|audio/wav');
    expect(captions.single.caption, 'Recorded cue: Working.');
    expect(captions.single.audioSha256, clip.audioSha256);
  });

  test('recorded asset player blocks native playback on hash mismatch',
      () async {
    final clip = recordedClip(
      audioSha256:
          'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
    );
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: 'Recorded cue: Working.',
      selectionSha256:
          'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      recordedReplay: false,
    );
    final backend = FakeNativeAudioBackend();
    final player = RowanRecordedAssetCuePlayer(
      assetBundle: FakeAssetBundle({
        'assets/${clip.assetKey}': Uint8List.fromList([9, 9, 9]),
      }),
      backend: backend,
    );

    await expectLater(
      player.play(playback),
      throwsA(isA<RowanActionCuePlaybackException>()),
    );

    expect(backend.played, isEmpty);
  });

  test('recorded asset player exposes stop and completion callbacks', () async {
    final backend = FakeNativeAudioBackend();
    final completed = <void>[];
    final stopped = <String>[];
    final player = RowanRecordedAssetCuePlayer(
      assetBundle: FakeAssetBundle({}),
      backend: backend,
      onComplete: () => completed.add(null),
      onStopped: () => stopped.add('stopped'),
    );

    await player.stop();
    backend.completed.add(null);
    await Future<void>.delayed(Duration.zero);
    await player.dispose();

    expect(backend.stopCalls, 1);
    expect(stopped, ['stopped']);
    expect(completed, hasLength(1));
    expect(backend.disposeCalls, 1);
  });

  test('bundled Cartesia asset passes hash gate with fake native backend',
      () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final clip = RowanActionClipRegistry.cartesiaActionPack()
        .clipFor(RowanActionCueKind.operationWorking)!;
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: 'Recorded cue: ${clip.caption}',
      selectionSha256:
          'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      recordedReplay: false,
    );
    final backend = FakeNativeAudioBackend();
    final player = RowanRecordedAssetCuePlayer(backend: backend);

    await player.play(playback);
    await player.dispose();

    expect(backend.played.single, '${clip.assetKey}|audio/wav');
    expect(clip.assetKey,
        'rowan/action-cues/cartesia-rowan-complete-pack/audio/cartesia-rowan-action-pack-working.wav');
  });
}
