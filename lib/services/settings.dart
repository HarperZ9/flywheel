// settings.dart — tiny persisted desktop settings, no plugin dependencies.
//
// Lives at ~/.flywheel/desktop.json beside the engine's own home
// (~/.flywheel/lanes.json), overridable with FLYWHEEL_HOME. Stores only UI
// state (theme mode); never credentials.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

class DesktopSettings {
  ThemeMode themeMode;
  DesktopSettings({this.themeMode = ThemeMode.system});

  static File _file() {
    final home = Platform.environment['FLYWHEEL_HOME'] ??
        '${Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '.'}'
            '${Platform.pathSeparator}.flywheel';
    return File('$home${Platform.pathSeparator}desktop.json');
  }

  static DesktopSettings load() {
    try {
      final f = _file();
      if (!f.existsSync()) return DesktopSettings();
      final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final mode = switch (j['theme']) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
      return DesktopSettings(themeMode: mode);
    } catch (e) {
      // A corrupt settings file must never block launch; fall back to system.
      debugPrint('settings load failed, using defaults: $e');
      return DesktopSettings();
    }
  }

  void save() {
    try {
      final f = _file();
      f.parent.createSync(recursive: true);
      final theme = switch (themeMode) {
        ThemeMode.light => 'light',
        ThemeMode.dark => 'dark',
        ThemeMode.system => 'system',
      };
      f.writeAsStringSync(jsonEncode({'theme': theme}));
    } catch (e) {
      debugPrint('settings save failed: $e');
    }
  }
}
