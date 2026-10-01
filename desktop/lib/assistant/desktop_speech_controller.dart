import 'dart:async';
import 'package:flutter/foundation.dart';
import 'voice.dart';

abstract interface class CancellableVoiceOutput implements VoiceOutput {
  Future<void> stop();
}

/// Session opt-in for new completed chat turns, independent of microphone input.
class DesktopSpeechController extends ChangeNotifier {
  DesktopSpeechController(
      {required this.createOutput,
      this.supported = true,
      this.timeout = const Duration(minutes: 4),
      this.stopTimeout = const Duration(seconds: 3)});
  final CancellableVoiceOutput Function() createOutput;
  final bool supported;
  final Duration timeout;
  final Duration stopTimeout;
  static const maxCharacters = 12000;
  CancellableVoiceOutput? _output;
  Future<void> _stopping = Future.value();
  bool enabled = false, muted = false, speaking = false;
  bool _disposed = false, _eligible = false, _closedTurn = false;
  int _epoch = 0;
  String? _turn, _error;
  String? get problem => _error;
  String get status => !supported
      ? 'Spoken replies unavailable on this platform. Typing works normally.'
      : _error ??
          (!enabled
              ? 'Speech off. Enable for new chat replies.'
              : muted
                  ? 'Muted. Typed replies remain available.'
                  : speaking
                      ? 'Reading the reply aloud.'
                      : 'Ready for the next completed reply.');

  void setEnabled(bool value) {
    if (_disposed || !supported) return;
    enabled = value;
    interrupt();
  }

  void setMuted(bool value) {
    if (_disposed) return;
    muted = value;
    interrupt();
  }

  void beginTurn(String id) {
    if (_disposed) return;
    interrupt();
    _turn = id;
    _closedTurn = false;
    _eligible = supported && enabled && !muted;
  }

  void interrupt() {
    if (_disposed) return;
    _epoch++;
    _eligible = false;
    speaking = false;
    _error = null;
    final output = _output;
    if (output != null) {
      _stopping = _stopping
          .then((_) => output.stop().timeout(stopTimeout))
          .catchError((Object _) {
        if (!_disposed) {
          _error =
              'Could not confirm speech stopped. Check device audio; typing still works.';
          notifyListeners();
        }
      });
    }
    notifyListeners();
  }

  Future<void> completeTurn(String id, String text) async {
    if (_disposed || _turn != id || _closedTurn) return;
    _closedTurn = true;
    if (!_eligible || text.trim().isEmpty) return;
    if (text.length > maxCharacters) {
      _error = 'Reply exceeds the speech limit. Read the full answer in chat.';
      notifyListeners();
      return;
    }
    final epoch = _epoch;
    await _stopping;
    if (_disposed || epoch != _epoch || !enabled || muted || _error != null) {
      return;
    }
    try {
      final output = _output ??= createOutput();
      speaking = true;
      notifyListeners();
      await output.speak(text).timeout(timeout);
    } on TimeoutException {
      if (!_disposed && epoch == _epoch) {
        interrupt();
        _error = 'Speech reached its time limit. Read the full answer in chat.';
      }
    } catch (_) {
      if (!_disposed && epoch == _epoch) {
        interrupt();
        _error =
            'Speech unavailable. Check the installed voice or audio output, then try the next reply.';
      }
    } finally {
      if (!_disposed && epoch == _epoch) speaking = false;
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    interrupt();
    _disposed = true;
    super.dispose();
  }
}
