import 'rowan_action_cue_clip_model.dart';
import 'rowan_action_cue_hash.dart';

enum RowanActionCueAudioSource { recordedClip, localSynthesis }

class RowanActionCuePlayback {
  const RowanActionCuePlayback({
    required this.source,
    required this.caption,
    required this.captionSha256,
    required this.textSha256,
    required this.audioSha256,
    required this.provenanceSha256,
    required this.recordedReplay,
    required this.mayTrainOrCloneFromAudio,
    required this.useRestriction,
    this.recordedClip,
    this.localSynthesisRef,
  });

  factory RowanActionCuePlayback.recordedClip({
    required RowanActionClip clip,
    required String caption,
    required String selectionSha256,
    required bool recordedReplay,
  }) {
    final provenance = rowanActionCueSha256({
      'source': RowanActionCueAudioSource.recordedClip.name,
      'clip_sha256': clip.clipSha256,
      'selection_sha256': selectionSha256,
      'text_sha256': clip.textSha256,
      'audio_sha256': clip.audioSha256,
    });
    return RowanActionCuePlayback(
      source: RowanActionCueAudioSource.recordedClip,
      caption: caption,
      captionSha256: rowanActionCueSha256(caption),
      textSha256: clip.textSha256,
      audioSha256: clip.audioSha256,
      provenanceSha256: provenance,
      recordedReplay: recordedReplay,
      mayTrainOrCloneFromAudio: false,
      useRestriction:
          'Playback only; do not use this generated clip for voice training or cloning.',
      recordedClip: clip,
    );
  }

  factory RowanActionCuePlayback.localSynthesis({
    required String localSynthesisRef,
    required String caption,
    required String textSha256,
    required String audioSha256,
  }) {
    final provenance = rowanActionCueSha256({
      'source': RowanActionCueAudioSource.localSynthesis.name,
      'local_synthesis_ref': localSynthesisRef,
      'text_sha256': textSha256,
      'audio_sha256': audioSha256,
    });
    return RowanActionCuePlayback(
      source: RowanActionCueAudioSource.localSynthesis,
      caption: caption,
      captionSha256: rowanActionCueSha256(caption),
      textSha256: textSha256,
      audioSha256: audioSha256,
      provenanceSha256: provenance,
      recordedReplay: false,
      mayTrainOrCloneFromAudio: false,
      useRestriction:
          'Locally synthesized speech; keep text and audio hashes with the playback receipt.',
      localSynthesisRef: localSynthesisRef,
    );
  }

  final RowanActionCueAudioSource source;
  final String caption;
  final String captionSha256;
  final String textSha256;
  final String audioSha256;
  final String provenanceSha256;
  final bool recordedReplay;
  final bool mayTrainOrCloneFromAudio;
  final String useRestriction;
  final RowanActionClip? recordedClip;
  final String? localSynthesisRef;
}

abstract interface class RowanActionCuePlayer {
  Stream<void> get completions;
  Future<void> play(RowanActionCuePlayback playback);
  Future<void> stop();
}

class SilentRowanActionCuePlayer implements RowanActionCuePlayer {
  const SilentRowanActionCuePlayer();

  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {}

  @override
  Future<void> stop() async {}
}

abstract interface class RowanRecordedClipPlayer {
  Future<void> play(RowanActionClip clip);
  Future<void> stop();
}

class RowanRecordedClipPlayerAdapter implements RowanActionCuePlayer {
  const RowanRecordedClipPlayerAdapter(this.player);

  final RowanRecordedClipPlayer player;

  @override
  Stream<void> get completions => const Stream.empty();

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    final clip = playback.recordedClip;
    if (clip == null) throw UnsupportedError('local synthesis is not mounted');
    await player.play(clip);
  }

  @override
  Future<void> stop() => player.stop();
}
