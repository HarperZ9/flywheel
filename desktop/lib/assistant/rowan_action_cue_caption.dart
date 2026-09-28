import 'rowan_action_cue_player.dart';

class RowanActionCueCaptionState {
  const RowanActionCueCaptionState({
    required this.caption,
    required this.captionSha256,
    required this.playbackProvenanceSha256,
    required this.recordedReplay,
    required this.source,
    this.operationRef,
    this.eventRef,
  });

  final String caption;
  final String captionSha256;
  final String playbackProvenanceSha256;
  final bool recordedReplay;
  final RowanActionCueAudioSource source;
  final String? operationRef;
  final String? eventRef;

  factory RowanActionCueCaptionState.fromPlayback(
    RowanActionCuePlayback playback, {
    String? operationRef,
    String? eventRef,
  }) =>
      RowanActionCueCaptionState(
        caption: playback.caption,
        captionSha256: playback.captionSha256,
        playbackProvenanceSha256: playback.provenanceSha256,
        recordedReplay: playback.recordedReplay,
        source: playback.source,
        operationRef: operationRef,
        eventRef: eventRef,
      );
}
