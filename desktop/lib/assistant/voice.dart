// voice.dart -- the assistant's ears and voice, behind interfaces.
//
// Speech in and speech out are the one part of the assistant that needs a real
// device: a microphone, a speaker, and a platform speech engine. They live behind
// two small interfaces so the panel is written and tested against them here, and
// the phone build supplies the real engine (speech_to_text for listening,
// flutter_tts for speaking; see docs/MOBILE-SETUP.md). The default is a silent
// stub, so a build with no speech engine simply has no voice, never a crash, and
// the assistant stays fully usable by typing.

/// Listens for one spoken command and returns its transcript, or null when nothing
/// was heard or speech is unavailable.
abstract interface class VoiceInput {
  Future<String?> listen();

  /// Whether a real speech engine is present. The stub returns false, so a panel
  /// hides the microphone when there is nothing behind it.
  bool get available;
}

/// Speaks a line back to the user.
abstract interface class VoiceOutput {
  Future<void> speak(String text);
}

/// The default when no speech engine is wired: no microphone, and speaking is a
/// no-op. A desktop build, or a phone build before the speech packages are added,
/// uses this and stays fully usable by typing.
class SilentVoice implements VoiceInput, VoiceOutput {
  const SilentVoice();

  @override
  bool get available => false;

  @override
  Future<String?> listen() async => null;

  @override
  Future<void> speak(String text) async {}
}
