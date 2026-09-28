// theme_typography_test.dart -- guards the two-typeface canon at the theme
// layer, on every OS and with no pixels.
//
// The defect this guards against: ThemeData(fontFamily: X) applies X only to
// the default text theme at construction. The later
// base.copyWith(textTheme: _textTheme(t)) in flywheel_theme.dart replaces that
// theme wholesale, and copyWith does NOT re-apply fontFamily. So any TextTheme
// slot that does not name its own family ships in the platform default font
// (Segoe UI, SF Pro), not Hanken Grotesk. That is how every plain TextButton
// (Skip / Back / Done and 50-odd others) shipped in the wrong font once the
// labelLarge slot was added without a family. These checks read the family
// string off each slot, so they run identically on Linux CI and Windows and
// can never flake on rasterization. The tour golden test only captures media.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

/// Every TextTheme getter, so a slot added later without a family is caught no
/// matter which slot it is.
List<TextStyle?> _allSlots(TextTheme tt) => [
      tt.displayLarge, tt.displayMedium, tt.displaySmall,
      tt.headlineLarge, tt.headlineMedium, tt.headlineSmall,
      tt.titleLarge, tt.titleMedium, tt.titleSmall,
      tt.bodyLarge, tt.bodyMedium, tt.bodySmall,
      tt.labelLarge, tt.labelMedium, tt.labelSmall,
    ];

/// The grotesk slots flywheel defines. labelSmall is checked apart as the mono
/// voice. A plain TextButton and tab labels resolve their style from
/// labelLarge, so its presence here is the direct guard for the button defect.
Map<String, TextStyle?> _groteskSlots(TextTheme tt) => {
      'headlineMedium': tt.headlineMedium,
      'titleLarge': tt.titleLarge,
      'titleMedium': tt.titleMedium,
      'titleSmall': tt.titleSmall,
      'bodyLarge': tt.bodyLarge,
      'bodyMedium': tt.bodyMedium,
      'bodySmall': tt.bodySmall,
      'labelLarge': tt.labelLarge,
    };

void main() {
  final builders = <String, ThemeData Function()>{
    'light': flywheelLightTheme,
    'dark': flywheelDarkTheme,
  };

  builders.forEach((brightness, build) {
    test('$brightness theme: every grotesk slot names the grotesk family', () {
      final tt = build().textTheme;
      _groteskSlots(tt).forEach((name, style) {
        expect(style, isNotNull, reason: '$name must be defined');
        expect(style!.fontFamily, kTextFamily,
            reason: '$name must name the grotesk family, not fall back to the '
                'platform default font');
      });
      expect(tt.labelSmall?.fontFamily, kMonoFamily,
          reason: 'labelSmall is the mono voice');
    });

    test('$brightness theme: no populated slot has a null family', () {
      final tt = build().textTheme;
      for (final style in _allSlots(tt)) {
        if (style != null) {
          expect(style.fontFamily, isNotNull,
              reason: 'a populated TextTheme slot with a null family ships in '
                  'the platform default font');
        }
      }
    });
  });

  test('a chosen family plumbs through every defined slot, guarding copyWith',
      () {
    // The deeper root cause was copyWith dropping the constructor fontFamily.
    // A user-chosen family must reach every slot the theme defines; if a slot
    // does not carry it, that slot is not naming its family at all.
    final tt = flywheelLightTheme(
            textFamily: 'Chosen Sans', monoFamily: 'Chosen Mono')
        .textTheme;
    _groteskSlots(tt).forEach((name, style) {
      expect(style!.fontFamily, 'Chosen Sans',
          reason: '$name must carry the chosen text family');
    });
    expect(tt.labelSmall?.fontFamily, 'Chosen Mono',
        reason: 'labelSmall must carry the chosen mono family');
  });
}
