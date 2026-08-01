// gateway_process.dart — the app can start the engine itself.
//
// An installed app ships the frozen engine at `engine/flywheel-gateway.exe`
// beside the app exe, so a clean machine needs no Python and no PATH setup:
// the bundled engine is launched by absolute path first. A dev checkout has
// no bundle, so `flywheel up` on PATH stays as the fallback. Stopping the
// app leaves a user-started gateway running only if it was already running.

import 'dart:io';

import 'package:flutter/foundation.dart';

class GatewayProcess {
  Process? _child;

  bool get startedByUs => _child != null;

  /// The bundled frozen engine's path for an app exe living in [exeDir]:
  /// `<exeDir>/engine/flywheel-gateway.exe`. Pure; existence is the caller's
  /// check. Split out so the resolution rule is testable without Platform.
  static String bundledEnginePathFor(String exeDir) {
    final sep = Platform.pathSeparator;
    return '$exeDir${sep}engine${sep}flywheel-gateway.exe';
  }

  /// The bundled engine beside this executable, or null when absent (dev
  /// checkout, or an install without the engine payload).
  static String? bundledEngine() {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final candidate = bundledEnginePathFor(exeDir);
    return File(candidate).existsSync() ? candidate : null;
  }

  /// Start the engine as a child process: the bundled exe when shipped,
  /// `flywheel up` from PATH otherwise. Returns an error message, or null
  /// on success. The gateway needs a few seconds to come up; callers keep
  /// polling.
  Future<String?> start({int port = 8799}) async {
    if (_child != null) return null;
    final bundled = bundledEngine();
    try {
      if (bundled != null) {
        _child = await Process.start(
          bundled,
          ['--port', '$port'],
          mode: ProcessStartMode.detachedWithStdio,
        );
      } else {
        _child = await Process.start(
          'flywheel',
          ['up', '--port', '$port'],
          mode: ProcessStartMode.detachedWithStdio,
          runInShell: true,
        );
      }
      return null;
    } on ProcessException catch (e) {
      debugPrint('gateway start failed: $e');
      _child = null;
      if (bundled != null) {
        return 'The bundled engine failed to start ($bundled). '
            'Reinstall Flywheel, or run `flywheel up` from a terminal.';
      }
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
