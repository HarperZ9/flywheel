// Shell tests: the app renders the sidebar with all destinations,
// navigation switches views, and the offline state names the command that
// fixes it.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/main.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';

void main() {
  testWidgets('App renders the shell with all twenty-four destinations',
      (WidgetTester tester) async {
    await tester.pumpWidget(FlywheelApp(settings: DesktopSettings()));
    await tester.pump();
    expect(find.text('Flywheel'), findsWidgets);
    expect(find.byType(SideRail), findsOneWidget);
    // In rail order (top to bottom) so the one-directional scroll below reveals
    // each in turn — the nav is grouped Start / Do / Know / Advanced.
    for (final label in [
      'Chat',
      'Compare',
      'Models',
      'Code',
      'Companion',
      'Plan',
      'Workflows',
      'Studio',
      'Lint',
      'Memory',
      'Graph',
      'Projects',
      'Feeds',
      'Discourse',
      'Academy',
      'Receipts',
      'Instruments',
      'Science',
      'World',
      'Lanes',
      'Train',
      'Uplift',
      'Family',
      'Plugins',
    ]) {
      // The rail scrolls when the window is short; bring each item in view.
      await tester.scrollUntilVisible(find.text(label), 40,
          scrollable: find.byType(Scrollable).first);
      expect(find.text(label), findsOneWidget);
    }
  });

  testWidgets('Navigation switches views and offline state names the command',
      (WidgetTester tester) async {
    // A tall window so the grouped rail fits without scrolling and every
    // destination is directly tappable.
    tester.view.physicalSize = const Size(1400, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(FlywheelApp(settings: DesktopSettings()));
    await tester.pump();
    // Offline (no gateway in the test environment): Chat, the default surface,
    // states the fact and names the command.
    expect(find.textContaining('flywheel up'), findsWidgets);
    // Switch to Receipts (now under Advanced); its offline state renders too.
    await tester.tap(find.text('Receipts'));
    await tester.pump();
    expect(find.textContaining('receipts ledger'), findsOneWidget);
  });
}
