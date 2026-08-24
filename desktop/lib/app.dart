import 'package:flutter/material.dart';

import 'services/settings.dart';
import 'shell/flywheel_shell.dart';
import 'theme/flywheel_theme.dart';
import 'widgets/system_text_scaler.dart' as scaler;

class FlywheelApp extends StatefulWidget {
  const FlywheelApp({
    super.key,
    required this.settings,
    this.dependencies,
  });

  final DesktopSettings settings;
  final FlywheelDependencies? dependencies;

  @override
  State<FlywheelApp> createState() => _FlywheelAppState();
}

class _FlywheelAppState extends State<FlywheelApp> {
  late ThemeMode _mode = widget.settings.themeMode;

  void _toggleTheme() {
    setState(() {
      _mode = switch (_mode) {
        ThemeMode.system => ThemeMode.light,
        ThemeMode.light => ThemeMode.dark,
        ThemeMode.dark => ThemeMode.system,
      };
      widget.settings.themeMode = _mode;
      widget.settings.save();
    });
  }

  void _appearanceChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final settings = widget.settings;
    return MaterialApp(
      title: 'Flywheel',
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(
        textFamily: settings.textFamily,
        monoFamily: settings.monoFamily,
        groundPreset: settings.groundPreset,
      ),
      darkTheme: flywheelDarkTheme(
        textFamily: settings.textFamily,
        monoFamily: settings.monoFamily,
        groundPreset: settings.groundPreset,
      ),
      themeMode: _mode,
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: scaler.ComposedTextScaler(
            system: MediaQuery.textScalerOf(context),
            userScale: settings.uiScale.clamp(0.8, 1.4),
          ),
        ),
        child: child!,
      ),
      home: FlywheelShell(
        themeMode: _mode,
        onToggleTheme: _toggleTheme,
        onAppearanceChanged: _appearanceChanged,
        settings: settings,
        dependencies: widget.dependencies,
      ),
    );
  }
}
