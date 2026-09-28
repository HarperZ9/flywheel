import 'rowan_action_cue_hash.dart';
import 'rowan_action_cue_models.dart';

class RowanActionClip {
  const RowanActionClip({
    required this.eventId,
    required this.clipId,
    required this.variantId,
    required this.assetKey,
    required this.caption,
    required this.category,
    required this.context,
    required this.prerequisite,
    required this.trigger,
    required this.textSha256,
    required this.audioSha256,
    required this.durationSeconds,
    required this.recommendedCooldownSeconds,
    required this.manifestSha256,
    required this.sourcePack,
    required this.generation,
    required this.provenanceBasis,
    this.priority,
    this.receiptFile,
  });

  final String eventId;
  final String clipId;
  final String variantId;
  final String assetKey;
  final String caption;
  final String category;
  final String context;
  final String prerequisite;
  final String trigger;
  final String textSha256;
  final String audioSha256;
  final double durationSeconds;
  final double recommendedCooldownSeconds;
  final String manifestSha256;
  final String sourcePack;
  final String generation;
  final String provenanceBasis;
  final String? priority;
  final String? receiptFile;

  Map<String, Object?> toJson() => {
        'event_id': eventId,
        'clip_id': clipId,
        'variant_id': variantId,
        'asset_key': assetKey,
        'caption': caption,
        'category': category,
        'context': context,
        'prerequisite': prerequisite,
        'trigger': trigger,
        'text_sha256': textSha256,
        'audio_sha256': audioSha256,
        'duration_seconds': durationSeconds,
        'recommended_cooldown_seconds': recommendedCooldownSeconds,
        'manifest_sha256': manifestSha256,
        'source_pack': sourcePack,
        'generation': generation,
        'provenance_basis': provenanceBasis,
        'priority': priority,
        'receipt_file': receiptFile,
      };

  String get clipSha256 => rowanActionCueSha256(toJson());
}

class RowanActionCueTelemetry {
  const RowanActionCueTelemetry({
    required this.kind,
    required this.eventRef,
    required this.eventSha256,
    required this.clipId,
    required this.clipSha256,
    required this.variantId,
    required this.clipSelectionSha256,
    required this.textSha256,
    required this.audioSha256,
    required this.captionSha256,
    required this.playbackProvenanceSha256,
    required this.recordedReplay,
    required this.provesTaskCorrectness,
    this.operationRef,
  });

  final RowanActionCueKind kind;
  final String eventRef, eventSha256, clipId, clipSha256;
  final String variantId, clipSelectionSha256;
  final String textSha256, audioSha256, captionSha256;
  final String playbackProvenanceSha256;
  final String? operationRef;
  final bool recordedReplay, provesTaskCorrectness;

  Map<String, Object?> toJson() => {
        'kind': kind.wire,
        'event_ref': eventRef,
        'event_sha256': eventSha256,
        'operation_ref': operationRef,
        'clip_id': clipId,
        'clip_sha256': clipSha256,
        'variant_id': variantId,
        'clip_selection_sha256': clipSelectionSha256,
        'text_sha256': textSha256,
        'audio_sha256': audioSha256,
        'caption_sha256': captionSha256,
        'playback_provenance_sha256': playbackProvenanceSha256,
        'recorded_replay': recordedReplay,
        'proves_task_correctness': provesTaskCorrectness,
      };
}
