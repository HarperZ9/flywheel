import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:flywheel_desktop/assistant/desktop_native_voice.dart';

class _Engine extends FlutterTts {
  final voices = Completer<dynamic>();
  final calls = <String>[];
  bool failSetup = false;
  int stopResult = 1;
  @override
  Future<dynamic> awaitSpeakCompletion(bool value) async {
    calls.add('await:$value');
    if (failSetup) throw StateError('setup failed');
    return 1;
  }

  @override
  Future<dynamic> get getVoices => voices.future;
  @override
  Future<dynamic> setVoice(Map<String, String> voice) async {
    calls.add('voice:${voice['name']}');
    return 1;
  }

  @override
  Future<dynamic> setPitch(double pitch) async {
    calls.add('pitch');
    return 1;
  }

  @override
  Future<dynamic> setSpeechRate(double rate) async {
    calls.add('rate');
    return 1;
  }

  @override
  Future<dynamic> speak(String text, {bool focus = false}) async {
    calls.add('speak:$text');
    return 1;
  }

  @override
  Future<dynamic> stop() async {
    calls.add('stop');
    return stopResult;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('cancel during setup shares tuning and only the latest turn speaks',
      () async {
    final engine = _Engine();
    final output = DesktopNativeVoice(engine: engine);
    final first = output.speak('Old answer');
    await Future<void>.delayed(Duration.zero);
    await output.stop();
    final second = output.speak('New <answer> & text');
    engine.voices.complete([
      {'name': 'Australian', 'locale': 'en-AU'}
    ]);
    await Future.wait([first, second]);
    expect(engine.calls.where((c) => c.startsWith('await:')), ['await:true']);
    expect(engine.calls.where((c) => c.startsWith('voice:')),
        ['voice:Australian']);
    expect(
        engine.calls.last,
        Platform.isWindows
            ? 'speak:New &lt;answer&gt; &amp; text'
            : 'speak:New <answer> & text');
    expect(engine.calls.where((c) => c.startsWith('speak:')), hasLength(1));
  });
  test('setup failure permits a fresh later attempt', () async {
    final engine = _Engine()..failSetup = true;
    final output = DesktopNativeVoice(engine: engine);
    await expectLater(output.speak('Failed'), throwsStateError);
    engine.failSetup = false;
    engine.voices.complete([]);
    await output.speak('Recovered');
    expect(engine.calls.last, 'speak:Recovered');
  });
  test('stop without native confirmation is a failure', () async {
    final engine = _Engine()..stopResult = 0;
    await expectLater(
        DesktopNativeVoice(engine: engine).stop(), throwsStateError);
  });
}
