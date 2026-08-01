// Appearance: the canon look is the DEFAULT, not the cage. Users choose
// their own text and mono families and a UI scale; the choice rides the
// theme extension so every widget follows, and color stays a verdict
// regardless of taste.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

void main() {
  test('canon families are the default', () {
    final t = flywheelLightTheme();
    final fw = t.extension<FwTokens>()!;
    expect(fw.textFamily, 'Hanken Grotesk');
    expect(fw.monoFamily, 'Conso');
  });

  test('user-chosen families ride the theme extension end to end', () {
    final t = flywheelDarkTheme(textFamily: 'Georgia', monoFamily: 'Consolas');
    final fw = t.extension<FwTokens>()!;
    expect(fw.textFamily, 'Georgia');
    expect(fw.monoFamily, 'Consolas');
    expect(fwMono(fw).fontFamily, 'Consolas');
    expect(fwKicker(fw).fontFamily, 'Consolas');
  });

  test('settings carry appearance choices with sane defaults', () {
    final s = DesktopSettings();
    expect(s.textFamily, isNull); // null = canon default
    expect(s.monoFamily, isNull);
    expect(s.groundPreset, isNull); // null = Ceramic, the canon ground
    expect(s.uiScale, 1.0);
    s.textFamily = 'Georgia';
    s.uiScale = 1.15;
    expect(s.uiScale, 1.15);
  });

  test('a ground preset moves the neutral, never the verdicts', () {
    final canon = flywheelLightTheme();
    final slate = flywheelLightTheme(groundPreset: 'Slate');
    final ct = canon.extension<FwTokens>()!;
    final st = slate.extension<FwTokens>()!;
    expect(st.ground, const Color(0xFFEDEFF2));
    expect(st.ground, isNot(ct.ground));
    expect(slate.scaffoldBackgroundColor, st.ground);
    // The verdict palette is not on the menu.
    expect(st.verified, ct.verified);
    expect(st.drift, ct.drift);
    expect(st.ink, ct.ink);
  });

  test('dark variants of a preset use the dark pair', () {
    final t = flywheelDarkTheme(groundPreset: 'Sand').extension<FwTokens>()!;
    expect(t.ground, const Color(0xFF13110C));
    expect(t.ground2, const Color(0xFF1C1913));
  });

  test('an unknown or null preset falls back to canon untouched', () {
    final canon = flywheelLightTheme().extension<FwTokens>()!;
    final bogus =
        flywheelLightTheme(groundPreset: 'Neon').extension<FwTokens>()!;
    expect(bogus.ground, canon.ground);
    expect(bogus.ground2, canon.ground2);
  });
}
