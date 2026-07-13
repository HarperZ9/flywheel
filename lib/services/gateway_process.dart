// gateway_process.dart — the app can start the engine itself.
//
// `flywheel up` launches the gateway on 127.0.0.1:8799. When the desktop
// app finds the gateway offline it offers to start it as a child process,
// so the user never needs a terminal. Stopping the app leaves a
// user-started gateway running only if it was already running before.

import 'dart:io';

import 'package:flutter/foundation.dart';

class GatewayProcess {
  Process? _child;

  bool get startedByUs => _child != null;

  /// Start `flywheel up` as a child process. Returns an error message, or
  /// null on success. The gateway needs a few seconds to come up; callers
  /// keep polling.
  Future<String?> start({int port = 8799}) async {
    if (_child != null) return null;
    try {
      _child = await Process.start(
        'flywheel',
        ['up', '--port', '$port'],
        mode: ProcessStartMode.detachedWithStdio,
        runInShell: true,
      );
      return null;
    } on ProcessException catch (e) {
      debugPrint('gateway start failed: $e');
      _child = null;
      return 'flywheel is not on PATH. Install the engine: pip install flywheel '
          '(or pip install -e . from the engine checkout), then retry.';
    }
  }

  /// Stop the child gateway if this app started it.
  void stopIfOwned() {
    final p = _child;
    if (p != null) {
      _child = null;
      try {
        p.kill();
      } catch (e) {
        debugPrint('gateway stop failed: $e');
      }
    }
  }
}
