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
  String? textFamily; // null = canon default (Hanken Grotesk)
  String? monoFamily; // null = canon default (Conso)
  String? groundPreset; // null = canon default (Ceramic)
  double uiScale;
  double railWidth; // width of the expanded side rail, drag-adjustable

  /// Reusable prompts the user saved, newest first: [{title, text}]. A small
  /// shelf so nobody starts from a blank composer every time.
  List<Map<String, String>> savedPrompts;

  DesktopSettings(
      {this.themeMode = ThemeMode.system,
      List<String>? recentWorkspaces,
      this.railCollapsed = false,
      this.textFamily,
      this.monoFamily,
      this.groundPreset,
      this.uiScale = 1.0,
      this.railWidth = 172,
      List<Map<String, String>>? savedPrompts})
      : recentWorkspaces = recentWorkspaces ?? [],
        savedPrompts = savedPrompts ?? [];

  /// Save a prompt to the shelf (deduped by text, newest first, capped at 30).
  void savePrompt(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    savedPrompts.removeWhere((p) => p['text'] == trimmed);
    final title = trimmed.replaceAll('\n', ' ');
    savedPrompts.insert(0, {
      'title': title.length <= 48 ? title : '${title.substring(0, 48)}…',
      'text': trimmed,
    });
    if (savedPrompts.length > 30) savedPrompts = savedPrompts.sublist(0, 30);
    save();
  }

  void removePrompt(String text) {
    savedPrompts.removeWhere((p) => p['text'] == text);
    save();
  }

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
        textFamily: j['text_family'] is String ? j['text_family'] : null,
        monoFamily: j['mono_family'] is String ? j['mono_family'] : null,
        groundPreset: j['ground_preset'] is String ? j['ground_preset'] : null,
        uiScale: j['ui_scale'] is num
            ? (j['ui_scale'] as num).toDouble().clamp(0.8, 1.4)
            : 1.0,
        railWidth: j['rail_width'] is num
            ? (j['rail_width'] as num).toDouble().clamp(148.0, 320.0)
            : 172,
        savedPrompts: (j['saved_prompts'] is List)
            ? [
                for (final p in j['saved_prompts'] as List)
                  if (p is Map &&
                      p['title'] is String &&
                      p['text'] is String)
                    {'title': p['title'] as String, 'text': p['text'] as String}
              ]
            : [],
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
        if (textFamily != null) 'text_family': textFamily,
        if (monoFamily != null) 'mono_family': monoFamily,
        if (groundPreset != null) 'ground_preset': groundPreset,
        'ui_scale': uiScale,
        'rail_width': railWidth,
        'saved_prompts': savedPrompts,
      }));
    } catch (e) {
      debugPrint('settings save failed: $e');
    }
  }
}
