import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/rowan_action_cue_hash.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_recorded_player.dart';

import 'rowan_action_cue_recorded_player_fixtures.dart';

void main() {
  test('recorded asset player does not start stale clip after stop', () async {
    final bytes = Uint8List.fromList([7, 7, 7, 7]);
    final clip = recordedClip(audioSha256: rowanActionCueBytesSha256(bytes));
    final bundle = PendingAssetBundle('assets/${clip.assetKey}', bytes);
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: 'Recorded cue: Working.',
      selectionSha256:
          'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      recordedReplay: false,
    );
    final backend = FakeNativeAudioBackend();
    final player = RowanRecordedAssetCuePlayer(
      assetBundle: bundle,
      backend: backend,
    );

    final play = player.play(playback);
    await bundle.started.future;
    final stop = player.stop();
    bundle.release.complete();

    await expectLater(
      play,
      throwsA(isA<RowanActionCuePlaybackException>()),
    );
    await stop;
    expect(backend.played, isEmpty);
  });

  test('recorded asset player suppresses caption when stop races native play',
      () async {
    final bytes = Uint8List.fromList([8, 8, 8, 8]);
    final clip = recordedClip(audioSha256: rowanActionCueBytesSha256(bytes));
    final playback = RowanActionCuePlayback.recordedClip(
      clip: clip,
      caption: 'Recorded cue: Working.',
      selectionSha256:
          'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
      recordedReplay: false,
    );
    final backend = PendingNativeAudioBackend();
    final captions = <RowanActionCuePlayback>[];
    final player = RowanRecordedAssetCuePlayer(
      assetBundle: FakeAssetBundle({'assets/${clip.assetKey}': bytes}),
      backend: backend,
      onCaption: captions.add,
    );

    final play = player.play(playback);
    await backend.firstPlayStarted.future;
    final stop = player.stop();
    backend.releaseFirstPlay.complete();

    await expectLater(
      play,
      throwsA(isA<RowanActionCuePlaybackException>()),
    );
    await stop;
    expect(captions, isEmpty);
    expect(backend.stops, ['stop']);
  });
}
