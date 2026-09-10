// Own one raw auth read until settlement, even after the UI deadline expires.
import 'dart:async';
import 'package:flutter/foundation.dart';

class OAuthStatus extends ChangeNotifier {
  Future<Map<String, dynamic>> Function() read;
  final VoidCallback onCompleted;
  Map<String, dynamic>? doc;
  String? error;
  bool _enabled = false, _disposed = false, _reading = false, _requested = false;
  bool _suspended = false;
  bool _awaitingCompletion = false;
  int _generation = 0;
  Timer? _poll, _deadline;

  OAuthStatus({required this.read, required this.onCompleted});

  bool get pending {
    final rows = doc?['providers'];
    return rows is List && rows.whereType<Map>().any((p) => p['pending'] == true);
  }

  void configure(Future<Map<String, dynamic>> Function() reader, bool enabled) {
    read = reader;
    _enabled = enabled;
    _generation++;
    _poll?.cancel();
    _deadline?.cancel();
    doc = null;
    error = null;
    _requested = enabled;
    _awaitingCompletion = false;
    if (enabled) refresh();
  }

  void refresh({bool afterAction = false}) {
    if (_disposed || !_enabled) return;
    _suspended = false;
    _awaitingCompletion |= afterAction;
    _generation++;
    _requested = true;
    _poll?.cancel();
    _read();
  }

  void suspend() {
    _generation++;
    _suspended = true;
    _requested = false;
    _poll?.cancel();
    _deadline?.cancel();
  }

  Future<void> _read() async {
    if (_disposed || !_enabled || _reading || _suspended) return;
    _reading = true;
    _requested = false;
    final generation = _generation;
    final wasPending = pending;
    bool current() => !_disposed && _enabled && generation == _generation;
    _deadline = Timer(const Duration(seconds: 15), () {
      if (current()) {
        error = 'Sign-in status is taking longer; waiting for the engine.';
        notifyListeners();
      }
    });
    try {
      final result = await read();
      if (!current()) return;
      doc = result;
      error = null;
      notifyListeners();
      if ((wasPending || _awaitingCompletion) && !pending) {
        _awaitingCompletion = false;
        onCompleted();
      }
    } catch (_) {
      if (current()) {
        error = 'Could not read sign-in status; retrying when the engine responds.';
        notifyListeners();
      }
    } finally {
      _reading = false;
      _deadline?.cancel();
      if (!_disposed && _enabled && !_suspended) {
        if (_requested) {
          _read();
        } else if (pending || error != null) {
          _poll = Timer(const Duration(seconds: 2), _read);
        }
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    _poll?.cancel();
    _deadline?.cancel();
    super.dispose();
  }
}
