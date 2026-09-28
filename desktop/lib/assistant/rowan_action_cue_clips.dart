import 'rowan_action_cue_clip_data_1.dart';
import 'rowan_action_cue_clip_data_2.dart';
import 'rowan_action_cue_clip_data_3.dart';
import 'rowan_action_cue_clip_data_4.dart';
import 'rowan_action_cue_clip_data_5.dart';
import 'rowan_action_cue_clip_data_6.dart';
import 'rowan_action_cue_clip_data_7.dart';
import 'rowan_action_cue_clip_data_8.dart';
import 'rowan_action_cue_clip_data_9.dart';
import 'rowan_action_cue_clip_data_10.dart';
import 'rowan_action_cue_clip_data_11.dart';
import 'rowan_action_cue_clip_data_12.dart';
import 'rowan_action_cue_clip_data_13.dart';
import 'rowan_action_cue_clip_data_14.dart';
import 'rowan_action_cue_clip_data_15.dart';
import 'rowan_action_cue_clip_data_16.dart';
import 'rowan_action_cue_clip_model.dart';
import 'rowan_action_cue_hash.dart';
import 'rowan_action_cue_models.dart';

class RowanActionClipSelection {
  const RowanActionClipSelection({
    required this.clip,
    required this.selectionSha256,
  });

  final RowanActionClip clip;
  final String selectionSha256;
}

class RowanActionClipRegistry {
  const RowanActionClipRegistry(this._clips);

  factory RowanActionClipRegistry.cartesiaActionPack() =>
      const RowanActionClipRegistry(_cartesiaCompletePackClips);

  factory RowanActionClipRegistry.cartesiaCompletePack() =>
      const RowanActionClipRegistry(_cartesiaCompletePackClips);

  factory RowanActionClipRegistry.byKind(
    Map<RowanActionCueKind, List<RowanActionClip>> clips,
  ) =>
      RowanActionClipRegistry({
        for (final entry in clips.entries) entry.key.wire: entry.value,
      });

  final Map<String, List<RowanActionClip>> _clips;

  Iterable<RowanActionClip> get clips sync* {
    for (final variants in _clips.values) {
      yield* variants;
    }
  }

  int get clipCount => _clips.values.fold(
        0,
        (count, variants) => count + variants.length,
      );

  RowanActionClip? clipFor(RowanActionCueKind kind) {
    final variants = _clips[kind.wire];
    if (variants == null || variants.isEmpty) return null;
    return variants.first;
  }

  RowanActionClipSelection? selectClip(
    RowanActionCueKind kind,
    String eventRef,
  ) {
    final variants = _clips[kind.wire];
    if (variants == null || variants.isEmpty) return null;
    final selectionSha256 = rowanActionCueSha256({
      'event_id': kind.wire,
      'event_ref': eventRef,
      'variant_ids': [for (final clip in variants) clip.variantId],
    });
    final index = int.parse(selectionSha256.substring(0, 8), radix: 16) %
        variants.length;
    return RowanActionClipSelection(
      clip: variants[index],
      selectionSha256: selectionSha256,
    );
  }
}

const _cartesiaCompletePackClips = <String, List<RowanActionClip>>{
  ...rowanCartesiaActionCueClipData1,
  ...rowanCartesiaActionCueClipData2,
  ...rowanCartesiaActionCueClipData3,
  ...rowanCartesiaActionCueClipData4,
  ...rowanCartesiaActionCueClipData5,
  ...rowanCartesiaActionCueClipData6,
  ...rowanCartesiaActionCueClipData7,
  ...rowanCartesiaActionCueClipData8,
  ...rowanCartesiaActionCueClipData9,
  ...rowanCartesiaActionCueClipData10,
  ...rowanCartesiaActionCueClipData11,
  ...rowanCartesiaActionCueClipData12,
  ...rowanCartesiaActionCueClipData13,
  ...rowanCartesiaActionCueClipData14,
  ...rowanCartesiaActionCueClipData15,
  ...rowanCartesiaActionCueClipData16,

};
