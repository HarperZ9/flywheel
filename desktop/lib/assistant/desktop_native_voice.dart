import 'dart:io';
import 'package:flutter_tts/flutter_tts.dart';
import 'desktop_speech_controller.dart';
import 'rowan_voice_profile.dart';

DesktopSpeechController createDesktopSpeech() => DesktopSpeechController(
    supported: Platform.isWindows || Platform.isMacOS,
    createOutput: () => DesktopNativeVoice());

/// Uses installed voices; constructed only after explicit speech opt-in.
class DesktopNativeVoice implements CancellableVoiceOutput {
  DesktopNativeVoice({FlutterTts? engine}) : _tts = engine ?? FlutterTts();
  final FlutterTts _tts;
  Future<void>? _tuning;
  int _epoch = 0;

  @override
  Future<void> speak(String text) async {
    final epoch = ++_epoch;
    // Share setup across cancelled turns, so old setup cannot retune a new one.
    final tuning = _tuning ??= _tune();
    try {
      await tuning;
    } catch (_) {
      if (identical(_tuning, tuning)) _tuning = null;
      rethrow;
    }
    if (epoch != _epoch) return;
    // The Windows plugin prepends SAPI XML; answer text must remain text.
    final spoken = Platform.isWindows
        ? text
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
        : text;
    final result = await _tts.speak(spoken);
    if (result != 1 && epoch == _epoch) {
      throw StateError('speech engine refused playback');
    }
  }

  Future<void> _tune() async {
    await _tts.awaitSpeakCompletion(true);
    final voices = RowanVoiceProfile.normalize(await _tts.getVoices);
    final voice = RowanVoiceProfile.select(voices);
    if (voice != null) {
      await _tts.setVoice({'name': voice['name']!, 'locale': voice['locale']!});
    }
    await _tts.setPitch(RowanVoiceProfile.pitch);
    await _tts.setSpeechRate(RowanVoiceProfile.speechRate);
  }

  @override
  Future<void> stop() async {
    _epoch++;
    if (await _tts.stop() != 1) {
      throw StateError('speech engine did not confirm stop');
    }
  }
}
