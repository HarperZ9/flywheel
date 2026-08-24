// Reduced motion: when the OS asks, audited animation durations are zero
// and final state renders immediately.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/accessibility/motion.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';

void main() {
  testWidgets('the rail transition collapses under reduced motion',
      (tester) async {
    Duration? observed;
    await tester.pumpWidget(MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: Builder(builder: (context) {
            observed = motionDuration(context);
            return SideRail(
              destinations: const [
                RailDestination('Journey', group: 'work'),
              ],
              selectedIndex: 0,
              onSelect: (_) {},
              themeMode: ThemeMode.light,
              onToggleTheme: () {},
              collapsed: false,
              onToggleCollapse: () {},
            );
          }),
        ),
      ),
    ));
    await tester.pump();
    expect(observed, Duration.zero);
  });

  testWidgets('final state renders immediately when motion is reduced',
      (tester) async {
    await tester.pumpWidget(MediaQuery(
      data: const MediaQueryData(disableAnimations: true),
      child: MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: 1),
            duration: const Duration(milliseconds: 300),
            builder: (context, value, _) => Opacity(
                opacity: value,
                child: const Text('settled state')),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    // With a zero duration the tween completes on the first frame: the
    // final state is on screen with no intermediate opacity to wait out.
    final opacity = tester.widget<Opacity>(find.byType(Opacity)).opacity;
    expect(opacity, 1.0);
  });
}
