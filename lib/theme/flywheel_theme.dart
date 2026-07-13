// flywheel_theme.dart — Flywheel's design token system ported from the CSS
// shell (site/index.html) to Flutter ThemeData.
//
// Verdict-color semantics: color ONLY ever means a verdict. Green = MATCH/verified,
// iris (blue-violet) = DRIFT, grey = UNVERIFIABLE. No decorative color. The
// "ceramic ground" light palette is the default; dark mode mirrors it.

import 'package:flutter/material.dart';

class FlywheelColors {
  // Verdict semantics (the only colors that carry meaning)
  static const match = Color(0xFF1F6B45);       // verified green
  static const drift = Color(0xFF4636E8);       // iris (changed)
  static const unverifiable = Color(0xFF8A5A12); // warm grey/amber (can't tell)

  // Status (lanes, endpoints)
  static const live = Color(0xFF1F6B45);
  static const declared = Color(0xFF8A5A12);
  static const missing = Color(0xFFB23B3B);

  // Light palette ("ceramic ground")
  static const lightBg = Color(0xFFF4F3EF);
  static const lightInk = Color(0xFF0B0C0E);
  static const lightMuted = Color(0xFF565A62);
  static const lightHair = Color(0x24111A18); // hairline border
  static const lightSurface = Color(0xFFFBFAF7);

  // Dark palette
  static const darkBg = Color(0xFF14041B);     // deep aubergine
  static const darkInk = Color(0xFFE8E4F0);
  static const darkMuted = Color(0xFF9683A8);
  static const darkHair = Color(0x33E8E4F0);
  static const darkSurface = Color(0xFF1E0E28);
}

ThemeData flywheelLightTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: FlywheelColors.lightBg,
    colorScheme: const ColorScheme.light(
      primary: FlywheelColors.drift,
      onPrimary: Colors.white,
      secondary: FlywheelColors.match,
      surface: FlywheelColors.lightSurface,
      onSurface: FlywheelColors.lightInk,
      error: FlywheelColors.missing,
    ),
    cardTheme: CardThemeData(
      color: FlywheelColors.lightSurface,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: FlywheelColors.lightHair, width: 1),
        borderRadius: BorderRadius.circular(8),
      ),
    ),
    dividerTheme:
        const DividerThemeData(color: FlywheelColors.lightHair, thickness: 1),
    textTheme: const TextTheme(
      bodyLarge: TextStyle(color: FlywheelColors.lightInk),
      bodyMedium: TextStyle(color: FlywheelColors.lightInk),
      bodySmall: TextStyle(color: FlywheelColors.lightMuted),
      titleLarge: TextStyle(
          color: FlywheelColors.lightInk, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(
          color: FlywheelColors.lightInk, fontWeight: FontWeight.w600),
      labelSmall:
          TextStyle(color: FlywheelColors.lightMuted, fontFamily: 'monospace'),
    ),
  );
}

ThemeData flywheelDarkTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: FlywheelColors.darkBg,
    colorScheme: ColorScheme.dark(
      primary: FlywheelColors.drift,
      onPrimary: Colors.white,
      secondary: FlywheelColors.match,
      surface: FlywheelColors.darkSurface,
      onSurface: FlywheelColors.darkInk,
      error: FlywheelColors.missing,
    ),
    cardTheme: CardThemeData(
      color: FlywheelColors.darkSurface,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: FlywheelColors.darkHair, width: 1),
        borderRadius: BorderRadius.circular(8),
      ),
    ),
    dividerTheme:
        const DividerThemeData(color: FlywheelColors.darkHair, thickness: 1),
    textTheme: const TextTheme(
      bodyLarge: TextStyle(color: FlywheelColors.darkInk),
      bodyMedium: TextStyle(color: FlywheelColors.darkInk),
      bodySmall: TextStyle(color: FlywheelColors.darkMuted),
      titleLarge: TextStyle(
          color: FlywheelColors.darkInk, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(
          color: FlywheelColors.darkInk, fontWeight: FontWeight.w600),
      labelSmall:
          TextStyle(color: FlywheelColors.darkMuted, fontFamily: 'monospace'),
    ),
  );
}

/// Maps a lane status string to its verdict color.
Color laneStatusColor(String status) {
  switch (status) {
    case 'live':
      return FlywheelColors.live;
    case 'declared':
      return FlywheelColors.declared;
    case 'missing':
    case 'stale':
      return FlywheelColors.missing;
    default:
      return FlywheelColors.unverifiable;
  }
}
