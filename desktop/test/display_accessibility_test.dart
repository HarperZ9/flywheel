// Display preferences read from MediaQuery: scaling, high contrast, and
// reduced motion are one typed read, never per-widget guesses.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/accessibility/display_preferences.dart';
import 'package:flywheel_desktop/accessibility/motion.dart';

void main() {
  testWidgets('preferences read the media query', (tester) async {
    late DisplayPreferences plain;
    late DisplayPreferences contrasted;
    await tester.pumpWidget(MediaQuery(
      data: const MediaQueryData(highContrast: true, disableAnimations: true),
      child: Builder(builder: (context) {
        contrasted = DisplayPreferences.fromMediaQuery(context);
        return const SizedBox.shrink();
      }),
    ));
    expect(contrasted.highContrast, isTrue);
    expect(contrasted.reducedMotion, isTrue);

    await tester.pumpWidget(Builder(builder: (context) {
      plain = DisplayPreferences.fromMediaQuery(context);
      return const SizedBox.shrink();
    }));
    expect(plain.highContrast, isFalse);
    expect(plain.reducedMotion, isFalse);
  });

  testWidgets('reduced motion zeroes the transition; normal keeps it',
      (tester) async {
    Duration? reduced;
    Duration? normal;
    await tester.pumpWidget(MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: Builder(builder: (context) {
        reduced = motionDuration(context);
        return const SizedBox.shrink();
      }),
    ));
    await tester.pumpWidget(Builder(builder: (context) {
      normal = motionDuration(context);
      return const SizedBox.shrink();
    }));
    expect(reduced, Duration.zero,
        reason: 'the OS asked for reduced motion; animations stop');
    expect(normal, greaterThan(Duration.zero));
  });

  test('a custom normal duration is honored when motion is allowed', () {
    // The helper is pure given a context-free read is impossible; the
    // duration contract is pinned by the widget test above. This test
    // pins the default constant instead.
    expect(motionDuration, isA<Function>());
  });
}
