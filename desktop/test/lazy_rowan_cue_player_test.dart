import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/lazy_rowan_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_hash.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_recorded_player.dart';

import 'rowan_action_cue_recorded_player_fixtures.dart';

const _selectionSha256 =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';

RowanActionCuePlayback _playbackFor(Uint8List bytes) {
  final clip = recordedClip(audioSha256: rowanActionCueBytesSha256(bytes));
  return RowanActionCuePlayback.recordedClip(
    clip: clip,
    caption: 'Recorded cue: Working.',
    selectionSha256: _selectionSha256,
    recordedReplay: false,
  );
}

void main() {
  test('startup stop and dispose do not create recorded audio player',
      () async {
    var creates = 0;
    final player = LazyRowanCuePlayer(create: () {
      creates++;
      return RowanRecordedAssetCuePlayer(
        assetBundle: FakeAssetBundle({}),
        backend: FakeNativeAudioBackend(),
      );
    });

    expect(creates, 0);

    await player.stop();
    await player.dispose();

    expect(creates, 0);
  });

  test('first play lazily creates one player and forwards lifecycle calls',
      () async {
    final bytes = Uint8List.fromList([1, 2, 3, 4]);
    final playback = _playbackFor(bytes);
    final clip = playback.recordedClip!;
    final backend = FakeNativeAudioBackend();
    var creates = 0;
    final player = LazyRowanCuePlayer(create: () {
      creates++;
      return RowanRecordedAssetCuePlayer(
        assetBundle: FakeAssetBundle({'assets/${clip.assetKey}': bytes}),
        backend: backend,
      );
    });
    final completions = <void>[];
    final subscription = player.completions.listen(completions.add);

    await player.play(playback);
    backend.completed.add(null);
    await Future<void>.delayed(Duration.zero);
    await player.stop();
    await player.dispose();
    await subscription.cancel();

    expect(creates, 1);
    expect(backend.played, ['${clip.assetKey}|audio/wav']);
    expect(completions, hasLength(1));
    expect(backend.stopCalls, 1);
    expect(backend.disposeCalls, 1);
  });

  test('dispose during pending first play prevents native audio start',
      () async {
    final bytes = Uint8List.fromList([7, 7, 7, 7]);
    final playback = _playbackFor(bytes);
    final clip = playback.recordedClip!;
    final bundle = PendingAssetBundle('assets/${clip.assetKey}', bytes);
    final backend = FakeNativeAudioBackend();
    final player = LazyRowanCuePlayer(
      create: () => RowanRecordedAssetCuePlayer(
        assetBundle: bundle,
        backend: backend,
      ),
    );

    final play = player.play(playback);
    await bundle.started.future;
    final dispose = player.dispose();
    bundle.release.complete();

    await expectLater(
      play,
      throwsA(isA<RowanActionCuePlaybackException>()),
    );
    await dispose;

    expect(backend.played, isEmpty);
    expect(backend.disposeCalls, 1);
    await expectLater(player.play(playback), throwsStateError);
  });
}
