import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/desktop_speech_controller.dart';

class FakeSpeech implements CancellableVoiceOutput {
  final spoken = <String>[];
  var stops = 0;
  bool fail = false;
  Completer<void>? pending;
  Completer<void>? stopPending;
  @override
  Future<void> speak(String text) async {
    spoken.add(text);
    if (fail) throw StateError('private device diagnostic');
    await pending?.future;
  }

  @override
  Future<void> stop() async {
    stops++;
    await stopPending?.future;
  }
}

void main() {
  test('cancelled completion queued behind stop never starts', () async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(createOutput: () => backend);
    speech.setEnabled(true);
    speech.beginTurn('first');
    await speech.completeTurn('first', 'First');
    backend.stopPending = Completer<void>();
    speech.beginTurn('queued');
    final queued = speech.completeTurn('queued', 'Must not start');
    speech.interrupt();
    backend.stopPending!.complete();
    await queued;
    expect(backend.spoken, ['First']);
    speech.dispose();
  });
  test('late old playback completion cannot clear new speaking state',
      () async {
    final old = Completer<void>();
    final backend = FakeSpeech()..pending = old;
    final speech = DesktopSpeechController(createOutput: () => backend);
    speech.setEnabled(true);
    speech.beginTurn('a');
    final first = speech.completeTurn('a', 'First');
    await Future<void>.delayed(Duration.zero);
    backend.pending = Completer<void>();
    speech.beginTurn('b');
    final second = speech.completeTurn('b', 'Second');
    await Future<void>.delayed(Duration.zero);
    old.complete();
    await first;
    expect(speech.speaking, isTrue);
    backend.pending!.complete();
    await second;
    expect(speech.speaking, isFalse);
    speech.dispose();
  });
  test('length and time bounds disclose why reading stopped', () async {
    final backend = FakeSpeech()..pending = Completer<void>();
    final speech = DesktopSpeechController(
        createOutput: () => backend, timeout: const Duration(milliseconds: 5));
    speech.setEnabled(true);
    speech.beginTurn('long');
    await speech.completeTurn(
        'long', 'x' * (DesktopSpeechController.maxCharacters + 1));
    expect(backend.spoken, isEmpty);
    expect(speech.status, contains('speech limit'));
    speech.beginTurn('slow');
    await speech.completeTurn('slow', 'Slow voice');
    await Future<void>.delayed(Duration.zero);
    expect(speech.status, contains('time limit'));
    expect(backend.stops, greaterThan(0));
    backend.pending!.complete();
    speech.dispose();
  });
  test('unconfirmed stop prevents the next reply from starting', () async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(
        createOutput: () => backend,
        stopTimeout: const Duration(milliseconds: 5));
    speech.setEnabled(true);
    speech.beginTurn('a');
    await speech.completeTurn('a', 'First');
    backend.stopPending = Completer<void>();
    speech.beginTurn('b');
    await speech.completeTurn('b', 'Must remain silent');
    expect(backend.spoken, ['First']);
    expect(speech.status, contains('Could not confirm speech stopped'));
    backend.stopPending!.complete();
    speech.dispose();
  });
  test('off by default, new completed answers only, duplicate close ignored',
      () async {
    final backend = FakeSpeech();
    var created = 0;
    final speech = DesktopSpeechController(createOutput: () {
      created++;
      return backend;
    });
    speech.beginTurn('old');
    speech.setEnabled(true);
    await speech.completeTurn('old', 'Do not replay this.');
    expect(created, 0);
    speech.beginTurn('new');
    await speech.completeTurn('new', 'The actual assistant answer.');
    await speech.completeTurn('new', 'The actual assistant answer.');
    expect(backend.spoken, ['The actual assistant answer.']);
    speech.dispose();
  });
  test('mute and a new turn stop playback; late completion never restarts it',
      () async {
    final backend = FakeSpeech()..pending = Completer<void>();
    final speech = DesktopSpeechController(createOutput: () => backend);
    speech.setEnabled(true);
    speech.beginTurn('a');
    final first = speech.completeTurn('a', 'First answer');
    await Future<void>.delayed(Duration.zero);
    speech.setMuted(true);
    await Future<void>.delayed(Duration.zero);
    expect(backend.stops, greaterThan(0));
    speech.beginTurn('b');
    backend.pending!.complete();
    await first;
    await speech.completeTurn('b', 'Must remain silent');
    expect(backend.spoken, ['First answer']);
    expect(speech.status, 'Muted. Typed replies remain available.');
    speech.dispose();
  });
  test('playback failure is visible and leaves later typed turns usable',
      () async {
    final backend = FakeSpeech()..fail = true;
    final speech = DesktopSpeechController(createOutput: () => backend);
    speech.setEnabled(true);
    speech.beginTurn('a');
    await speech.completeTurn('a', 'Answer remains in chat');
    expect(speech.status, contains('Speech unavailable'));
    expect(speech.status, isNot(contains('private')));
    backend.fail = false;
    speech.beginTurn('b');
    await speech.completeTurn('b', 'Next answer');
    expect(backend.spoken.last, 'Next answer');
    speech.dispose();
  });
  test('unsupported platform never constructs the speech engine', () async {
    final speech = DesktopSpeechController(
        supported: false,
        createOutput: () => throw StateError('must not construct'));
    speech.setEnabled(true);
    speech.beginTurn('a');
    await speech.completeTurn('a', 'Silent');
    expect(speech.enabled, isFalse);
    expect(speech.status, contains('unavailable'));
    speech.dispose();
  });
}
