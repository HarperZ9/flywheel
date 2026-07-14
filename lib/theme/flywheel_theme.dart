// flywheel_theme.dart — builds Flutter ThemeData from the canon tokens.
//
// Typography: Hanken Grotesk carries all text; hierarchy comes from weight
// (800 display, 700/600 titles, 400 body), never a third family. Conso is
// the mono voice for labels, hashes, and numerals (applied per-widget via
// FwText styles, plus labelSmall here).

import 'package:flutter/material.dart';

import 'tokens.dart';

export 'tokens.dart';

const kTextFamily = 'Hanken Grotesk';
const kMonoFamily = 'Conso';

/// Theme builders. The canon pair is the default; a user-chosen family
/// rides the tokens so every widget follows without re-plumbing.
ThemeData flywheelLightTheme({String? textFamily, String? monoFamily}) =>
    _themeFrom(
        FwTokens.light.copyWith(
            textFamily: textFamily, monoFamily: monoFamily),
        Brightness.light);
ThemeData flywheelDarkTheme({String? textFamily, String? monoFamily}) =>
    _themeFrom(
        FwTokens.dark.copyWith(textFamily: textFamily, monoFamily: monoFamily),
        Brightness.dark);

ThemeData _themeFrom(FwTokens t, Brightness brightness) {
  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    fontFamily: t.textFamily,
    scaffoldBackgroundColor: t.ground,
    extensions: [t],
    colorScheme: ColorScheme(
      brightness: brightness,
      primary: t.drift,
      onPrimary: brightness == Brightness.light ? Colors.white : t.ground,
      secondary: t.verified,
      onSecondary: brightness == Brightness.light ? Colors.white : t.ground,
      error: t.drift,
      onError: brightness == Brightness.light ? Colors.white : t.ground,
      surface: t.ground,
      onSurface: t.ink,
    ),
  );

  return base.copyWith(
    dividerTheme: DividerThemeData(color: t.line, thickness: 1, space: 1),
    textTheme: _textTheme(t),
    iconTheme: IconThemeData(color: t.inkMuted, size: 18),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: t.drift,
      selectionColor: t.drift.withValues(alpha: 0.22),
      selectionHandleColor: t.drift,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: t.drift,
        foregroundColor:
            brightness == Brightness.light ? Colors.white : t.ground,
        textStyle: TextStyle(
            fontFamily: t.textFamily,
            fontWeight: FontWeight.w600,
            fontSize: 13),
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall)),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: t.inkSoft,
        side: BorderSide(color: t.line),
        textStyle: TextStyle(
            fontFamily: t.textFamily,
            fontWeight: FontWeight.w600,
            fontSize: 13),
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall)),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: t.panel,
      hintStyle: TextStyle(color: t.inkFaint, fontSize: 13.5),
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        borderSide: BorderSide(color: t.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        borderSide: BorderSide(color: t.drift, width: 1.5),
      ),
    ),
    scrollbarTheme: ScrollbarThemeData(
      thumbColor: WidgetStatePropertyAll(t.line),
      thickness: const WidgetStatePropertyAll(6),
      radius: const Radius.circular(3),
    ),
  );
}

TextTheme _textTheme(FwTokens t) {
  return TextTheme(
    // Display / titles: weight carries hierarchy.
    headlineMedium: TextStyle(
        color: t.ink,
        fontWeight: FontWeight.w800,
        fontSize: 26,
        height: 1.1,
        letterSpacing: -0.3),
    titleLarge: TextStyle(
        color: t.ink, fontWeight: FontWeight.w700, fontSize: 19, height: 1.15),
    titleMedium: TextStyle(
        color: t.ink, fontWeight: FontWeight.w600, fontSize: 15, height: 1.2),
    titleSmall: TextStyle(
        color: t.inkSoft, fontWeight: FontWeight.w600, fontSize: 13.5),
    // Body
    bodyLarge: TextStyle(color: t.inkSoft, fontSize: 14.5, height: 1.55),
    bodyMedium: TextStyle(color: t.inkSoft, fontSize: 13.5, height: 1.5),
    bodySmall: TextStyle(color: t.inkMuted, fontSize: 12.5, height: 1.45),
    // Mono voice
    labelSmall: TextStyle(
        color: t.inkFaint,
        fontFamily: t.monoFamily,
        fontSize: 11,
        letterSpacing: 0.4),
  );
}

/// The mono data style: the mono family with tabular figures, for hashes,
/// counts, versions, and table cells. Size and color overridable per use.
TextStyle fwMono(FwTokens t,
    {double size = 12.5, Color? color, FontWeight weight = FontWeight.w400}) {
  return TextStyle(
    fontFamily: t.monoFamily,
    fontSize: size,
    fontWeight: weight,
    color: color ?? t.inkSoft,
    fontFeatures: const [FontFeature.tabularFigures()],
  );
}

/// The kicker style: mono uppercase, wide-tracked. The section voice.
TextStyle fwKicker(FwTokens t, {Color? color, double size = 10.5}) {
  return TextStyle(
    fontFamily: t.monoFamily,
    fontSize: size,
    fontWeight: FontWeight.w600,
    letterSpacing: 2.2,
    color: color ?? t.inkFaint,
  );
}
