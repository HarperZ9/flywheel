// rowan_voice_profile.dart -- how Rowan sounds when a device speaks its replies.
//
// Rowan is the face and the voice of Flywheel, so the spoken voice is a
// deliberate choice: a soft male voice in an Australian or English accent, at a
// lowered pitch and unhurried pace. This file holds that choice as data and as
// one pure function, with no dependency on the speech plugin, so the selection
// is unit-tested on its own. speech_voice.dart reads these values and applies
// them to the real engine.
//
// The male preference is best effort. flutter_tts does not report a voice
// gender on every platform, so on a device that reports none the accent and the
// lowered pitch and pace carry the character. The voice is rendered by the
// device's own speech engine, so it is a chosen rendering. When a device has no
// matching voice installed, the engine keeps its default so a reply is still
// spoken.

/// The spoken-voice profile for Rowan, and the logic that picks the closest
/// installed voice to it.
abstract final class RowanVoiceProfile {
  /// Accents Rowan prefers, best first. Australian leads, then English. Any
  /// other English voice is a last resort before the engine default.
  static const preferredLocales = <String>['en-AU', 'en-GB'];

  /// A slightly lowered pitch reads as calm and smooth rather than bright.
  /// The flutter_tts pitch scale runs 0.5 to 2.0 with 1.0 as the neutral point.
  static const pitch = 0.94;

  /// An unhurried pace, considered rather than sleepy. The flutter_tts rate
  /// scale runs 0.0 to 1.0 on most platforms, where about half is natural
  /// speech.
  static const speechRate = 0.46;

  /// Coerces the raw list from `FlutterTts.getVoices` into the shape [select]
  /// reads: a list of string maps that each carry at least a name and a locale.
  /// Anything without both is dropped, so a malformed entry cannot crash the
  /// pick.
  static List<Map<String, String>> normalize(Object? raw) {
    if (raw is! List) return const <Map<String, String>>[];
    final out = <Map<String, String>>[];
    for (final item in raw) {
      if (item is! Map) continue;
      final voice = <String, String>{};
      item.forEach((key, value) {
        if (key != null && value != null) {
          voice[key.toString()] = value.toString();
        }
      });
      if (voice.containsKey('name') && voice.containsKey('locale')) {
        out.add(voice);
      }
    }
    return out;
  }

  /// Picks the installed voice that best matches Rowan.
  ///
  /// [voices] is a normalized list from [normalize]. A voice ranks first on a
  /// male gender when the engine reports one, then on accent (Australian, then
  /// English, then any other English locale). flutter_tts does not report a
  /// gender on every platform. Where it reports none, that term stays neutral
  /// for every voice, so accent decides and the lowered pitch and pace carry the
  /// character. Ties keep the engine's own order. Returns null when no English
  /// voice is installed, which tells the caller to leave the engine default in
  /// place.
  static Map<String, String>? select(List<Map<String, String>> voices) {
    Map<String, String>? best;
    int? bestRank;
    for (final voice in voices) {
      final locale = (voice['locale'] ?? '').replaceAll('_', '-').toLowerCase();
      if (!locale.startsWith('en')) continue;
      final region = locale.contains('-') ? locale.split('-')[1] : '';
      final localeRank = region == 'au'
          ? 0
          : region == 'gb'
              ? 1
              : 2;
      final gender = (voice['gender'] ?? '').toLowerCase();
      final genderRank = gender == 'male'
          ? 0
          : gender == 'female'
              ? 2
              : 1;
      final rank = genderRank * 10 + localeRank;
      if (bestRank == null || rank < bestRank) {
        bestRank = rank;
        best = voice;
      }
    }
    return best;
  }
}
