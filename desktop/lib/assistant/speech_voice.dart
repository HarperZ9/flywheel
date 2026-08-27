// speech_voice.dart -- the real ears and voice, on a device that has them.
//
// SpeechVoiceInput listens for one spoken command with speech_to_text, and
// FlutterTtsVoiceOutput speaks a line back with flutter_tts. Both sit behind the
// VoiceInput and VoiceOutput interfaces the panel is written against, so the phone
// build plugs them in and nothing in the tested core changes. Desktop builds keep
// the SilentVoice stub, so only a device with a microphone grows a microphone.

import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

import 'voice.dart';

/// Listens for one spoken command with the platform speech engine. It initializes
/// lazily on the first listen, and returns null when speech is unavailable or
/// nothing final was heard, so the panel falls back to typing without a crash.
class SpeechVoiceInput implements VoiceInput {
  SpeechVoiceInput({SpeechToText? engine}) : _stt = engine ?? SpeechToText();

  final SpeechToText _stt;
  bool _ready = false;

  @override
  bool get available => true;

  Future<bool> _ensure() async {
    if (_ready) return true;
    _ready = await _stt.initialize();
    return _ready;
  }

  @override
  Future<String?> listen() async {
    if (!await _ensure()) return null;
    final done = Completer<String?>();
    await _stt.listen(
      onResult: (r) {
        if (r.finalResult && !done.isCompleted) {
          done.complete(r.recognizedWords);
        }
      },
      listenOptions: SpeechListenOptions(listenFor: const Duration(seconds: 8)),
    );
    return done.future;
  }
}

/// Speaks a line back through the platform text-to-speech engine.
class FlutterTtsVoiceOutput implements VoiceOutput {
  FlutterTtsVoiceOutput({FlutterTts? engine}) : _tts = engine ?? FlutterTts();

  final FlutterTts _tts;

  @override
  Future<void> speak(String text) async {
    await _tts.speak(text);
  }
}
