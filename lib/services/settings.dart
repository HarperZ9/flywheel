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
  List<String> recentWorkspaces;
  bool railCollapsed;
  DesktopSettings(
      {this.themeMode = ThemeMode.system,
      List<String>? recentWorkspaces,
      this.railCollapsed = false})
      : recentWorkspaces = recentWorkspaces ?? [];

  /// Record a workspace as most-recently used (keeps the last six).
  void rememberWorkspace(String path) {
    recentWorkspaces.remove(path);
    recentWorkspaces.insert(0, path);
    if (recentWorkspaces.length > 6) {
      recentWorkspaces = recentWorkspaces.sublist(0, 6);
    }
    save();
  }

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
      return DesktopSettings(
        themeMode: mode,
        recentWorkspaces: (j['recent_workspaces'] is List)
            ? List<String>.from(j['recent_workspaces'])
            : [],
        railCollapsed: j['rail_collapsed'] == true,
      );
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
      f.writeAsStringSync(jsonEncode({
        'theme': theme,
        'recent_workspaces': recentWorkspaces,
        'rail_collapsed': railCollapsed,
      }));
    } catch (e) {
      debugPrint('settings save failed: $e');
    }
  }
}
