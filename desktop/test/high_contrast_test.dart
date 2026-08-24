// High contrast: when the OS asks for it, ink and hairlines meet the WCAG
// thresholds (4.5:1 normal text, 3:1 large text and boundaries) while the
// verdict hues keep their meaning.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';

double _luminance(Color c) {
  double linear(double channel) => channel <= 0.03928
      ? channel / 12.92
      : math.pow((channel + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b);
}

double contrastRatio(Color a, Color b) {
  final la = _luminance(a);
  final lb = _luminance(b);
  final lighter = la > lb ? la : lb;
  final darker = la > lb ? lb : la;
  return (lighter + 0.05) / (darker + 0.05);
}

void main() {
  test('high-contrast light ink meets 4.5:1 against its grounds', () {
    final hc = FwTokens.light.highContrast();
    for (final ground in [hc.ground, hc.ground2]) {
      expect(contrastRatio(hc.ink, ground), greaterThanOrEqualTo(4.5));
      expect(contrastRatio(hc.inkMuted, ground), greaterThanOrEqualTo(4.5));
    }
  });

  test('high-contrast dark ink meets 4.5:1 against its grounds', () {
    final hc = FwTokens.dark.highContrast();
    for (final ground in [hc.ground, hc.ground2]) {
      expect(contrastRatio(hc.ink, ground), greaterThanOrEqualTo(4.5));
      expect(contrastRatio(hc.inkMuted, ground), greaterThanOrEqualTo(4.5));
    }
  });

  test('hairlines meet the 3:1 component boundary in high contrast', () {
    for (final base in [FwTokens.light, FwTokens.dark]) {
      final hc = base.highContrast();
      expect(contrastRatio(hc.line, hc.ground), greaterThanOrEqualTo(3.0));
    }
  });

  test('verdict hues survive the mode unchanged', () {
    final hc = FwTokens.light.highContrast();
    expect(hc.verified, FwTokens.light.verified);
    expect(hc.drift, FwTokens.light.drift);
    expect(hc.unverifiable, FwTokens.light.unverifiable);
  });

  testWidgets('the theme builder serves the variant on request',
      (tester) async {
    final normal = flywheelLightTheme();
    final hc = flywheelLightTheme(highContrast: true);
    final normalTokens = normal.extension<FwTokens>()!;
    final hcTokens = hc.extension<FwTokens>()!;
    expect(hcTokens.ink, isNot(normalTokens.ink));
    expect(hcTokens.line, isNot(normalTokens.line));
  });
}
