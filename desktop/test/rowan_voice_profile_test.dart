import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/rowan_voice_profile.dart';

void main() {
  group('RowanVoiceProfile.select', () {
    test('prefers an Australian male voice above every other', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'us-female', 'locale': 'en-US', 'gender': 'female'},
        {'name': 'gb-male', 'locale': 'en-GB', 'gender': 'male'},
        {'name': 'au-male', 'locale': 'en-AU', 'gender': 'male'},
        {'name': 'au-female', 'locale': 'en-AU', 'gender': 'female'},
      ]);
      expect(chosen?['name'], 'au-male');
    });

    test('falls back to an English male voice when no Australian voice exists',
        () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'us-male', 'locale': 'en-US', 'gender': 'male'},
        {'name': 'gb-male', 'locale': 'en-GB', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'gb-male');
    });

    test('prefers a reported male voice over accent: an English male voice '
        'beats an Australian voice of unknown gender', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'au-unknown', 'locale': 'en-AU'},
        {'name': 'gb-male', 'locale': 'en-GB', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'gb-male');
    });

    test('a reported male voice beats a female voice of a preferred accent: '
        'an English male voice beats an Australian female one', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'au-female', 'locale': 'en-AU', 'gender': 'female'},
        {'name': 'gb-male', 'locale': 'en-GB', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'gb-male');
    });

    test('with no reported gender, accent decides: an Australian voice beats '
        'an English one', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'gb-unknown', 'locale': 'en-GB'},
        {'name': 'au-unknown', 'locale': 'en-AU'},
      ]);
      expect(chosen?['name'], 'au-unknown');
    });

    test('within one accent, a reported male voice beats an unmarked one', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'au-unknown', 'locale': 'en-AU'},
        {'name': 'au-male', 'locale': 'en-AU', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'au-male');
    });

    test('accepts underscores and case in the locale tag', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'au', 'locale': 'en_au'},
      ]);
      expect(chosen?['name'], 'au');
    });

    test('takes any English voice before giving up', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'us', 'locale': 'en-US'},
        {'name': 'fr', 'locale': 'fr-FR', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'us');
    });

    test('returns null when no English voice is installed', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'fr', 'locale': 'fr-FR', 'gender': 'male'},
        {'name': 'de', 'locale': 'de-DE'},
      ]);
      expect(chosen, isNull);
    });

    test('returns null for an empty voice list', () {
      expect(RowanVoiceProfile.select(const []), isNull);
    });

    test('keeps engine order on a tie', () {
      final chosen = RowanVoiceProfile.select([
        {'name': 'first', 'locale': 'en-AU', 'gender': 'male'},
        {'name': 'second', 'locale': 'en-AU', 'gender': 'male'},
      ]);
      expect(chosen?['name'], 'first');
    });
  });

  group('RowanVoiceProfile.normalize', () {
    test('coerces a plugin list of dynamic maps to string maps', () {
      final voices = RowanVoiceProfile.normalize(<dynamic>[
        <dynamic, dynamic>{'name': 'a', 'locale': 'en-AU'},
        <dynamic, dynamic>{'name': 'b', 'locale': 'en-GB', 'gender': 'male'},
      ]);
      expect(voices, hasLength(2));
      expect(voices.first['name'], 'a');
      expect(voices[1]['gender'], 'male');
    });

    test('drops entries missing a name or a locale', () {
      final voices = RowanVoiceProfile.normalize(<dynamic>[
        <dynamic, dynamic>{'name': 'a'},
        <dynamic, dynamic>{'locale': 'en-AU'},
        <dynamic, dynamic>{'name': 'ok', 'locale': 'en-AU'},
      ]);
      expect(voices, hasLength(1));
      expect(voices.single['name'], 'ok');
    });

    test('returns an empty list for a non-list input', () {
      expect(RowanVoiceProfile.normalize(null), isEmpty);
      expect(RowanVoiceProfile.normalize('nope'), isEmpty);
    });

    test('the chosen voice round-trips from normalize into select', () {
      final voices = RowanVoiceProfile.normalize(<dynamic>[
        <dynamic, dynamic>{'name': 'us', 'locale': 'en-US', 'gender': 'female'},
        <dynamic, dynamic>{'name': 'au', 'locale': 'en-AU', 'gender': 'male'},
      ]);
      expect(RowanVoiceProfile.select(voices)?['name'], 'au');
    });
  });

  test('the profile keeps a soft, unhurried pitch and rate', () {
    expect(RowanVoiceProfile.pitch, lessThan(1.0));
    expect(RowanVoiceProfile.speechRate, greaterThan(0.0));
    expect(RowanVoiceProfile.speechRate, lessThan(1.0));
    expect(RowanVoiceProfile.preferredLocales.first, 'en-AU');
  });
}
