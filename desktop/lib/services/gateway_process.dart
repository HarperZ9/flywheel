// gateway_process.dart — the app can start the engine itself.
//
// An installed app ships the frozen engine at `engine/flywheel-gateway.exe`
// beside the app exe, so a clean machine needs no Python and no PATH setup:
// the bundled engine is launched by absolute path first. A dev checkout has
// no bundle, so `flywheel up` on PATH stays as the fallback. Stopping the
// app leaves a user-started gateway running only if it was already running.

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

typedef GatewayProcessStarter = Future<Process> Function(
  String executable,
  List<String> arguments, {
  required ProcessStartMode mode,
  required bool runInShell,
});

class GatewayProcess {
  GatewayProcess({
    GatewayProcessStarter? processStarter,
    String? Function()? bundledEngineResolver,
  })  : _processStarter = processStarter ?? Process.start,
        _bundledEngineResolver = bundledEngineResolver ?? bundledEngine;

  final GatewayProcessStarter _processStarter;
  final String? Function() _bundledEngineResolver;
  Process? _child;
  Future<String?>? _starting;
  int _generation = 0;

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
  Future<String?> start({int port = 8799}) => _start(port, false);

  /// Automatic startup cannot silently change to an external PATH command.
  Future<String?> startBundled({int port = 8799}) => _start(port, true);

  Future<String?> _start(int port, bool requireBundled) {
    if (_child != null) return Future.value();
    if (_starting != null) return _starting!;
    final launch = _launch(port, ++_generation, requireBundled);
    _starting = launch;
    return launch.whenComplete(() {
      if (identical(_starting, launch)) _starting = null;
    });
  }

  Future<String?> _launch(int port, int generation, bool requireBundled) async {
    final bundled = _bundledEngineResolver();
    if (requireBundled && bundled == null) {
      return 'The bundled engine is unavailable. Reinstall Flywheel to restore it.';
    }
    final executable =
        bundled ?? (Platform.isWindows ? 'flywheel.exe' : 'flywheel');
    if (Platform.isWindows && !executable.toLowerCase().endsWith('.exe')) {
      return 'Windows startup requires an executable engine, not a script wrapper.';
    }
    try {
      final child = await _processStarter(
        executable,
        [if (bundled == null) 'up', '--port', '$port'],
        // Dart uses CREATE_NO_WINDOW for this mode on Windows. Detached
        // shell wrappers can give their children a visible console instead.
        mode: ProcessStartMode.normal,
        runInShell: false,
      );
      _child = child;
      _observe(child);
      if (generation != _generation) {
        stopIfOwned();
        return 'Engine start was cancelled.';
      }
      return null;
    } on ProcessException {
      debugPrint('gateway start failed');
      if (bundled != null) {
        return 'The bundled engine failed to start ($bundled). '
            'Reinstall Flywheel, or run `flywheel up` from a terminal.';
      }
      if (Platform.isWindows) {
        return 'flywheel.exe is not available on PATH. Install the engine with '
            'pip install flywheel-verify, or reinstall Flywheel. Windows script '
            'wrappers are not supported for automatic startup.';
      }
      return 'flywheel is not on PATH. Install the engine: pip install flywheel-verify '
          '(or pip install -e . from a checkout), then retry.';
    }
  }

  void _observe(Process child) {
    // Drain without retaining or printing output: it can contain private data,
    // and unread pipes can block an otherwise healthy gateway.
    unawaited(child.stdout.drain<void>().catchError((Object _) {}));
    unawaited(child.stderr.drain<void>().catchError((Object _) {}));
    unawaited(child.stdin.close().catchError((Object _) {}));
    unawaited(child.exitCode.then<void>((_) {
      if (identical(_child, child)) _child = null;
    }, onError: (Object _) {
      // An observation error does not prove exit; retain stop ownership.
    }));
  }

  /// Stop the child gateway if this app started it.
  void stopIfOwned() {
    _generation++;
    final p = _child;
    if (p != null) {
      try {
        if (p.kill() && identical(_child, p)) _child = null;
      } catch (_) {
        debugPrint('gateway stop failed');
      }
    }
  }
}
