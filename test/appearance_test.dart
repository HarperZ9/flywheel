// Appearance: the canon look is the DEFAULT, not the cage. Users choose
// their own text and mono families and a UI scale; the choice rides the
// theme extension so every widget follows, and color stays a verdict
// regardless of taste.
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
    expect(s.uiScale, 1.0);
    s.textFamily = 'Georgia';
    s.uiScale = 1.15;
    expect(s.uiScale, 1.15);
  });
}
