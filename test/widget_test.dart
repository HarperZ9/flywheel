// Shell tests: the app renders the sidebar with all five destinations,
// navigation switches views, and the offline state names the command that
// fixes it.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/main.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';

void main() {
  testWidgets('App renders the shell with all twenty destinations',
      (WidgetTester tester) async {
    await tester.pumpWidget(FlywheelApp(settings: DesktopSettings()));
    await tester.pump();
    expect(find.text('Flywheel'), findsWidgets);
    expect(find.byType(SideRail), findsOneWidget);
    for (final label in [
      'Projects',
      'Plan',
      'Lanes',
      'Family',
      'Code',
      'Lint',
      'World',
      'Graph',
      'Feeds',
      'Receipts',
      'Companion',
      'Agent',
      'Workflows',
      'Studio',
      'Science',
      'Train',
      'Uplift',
      'Memory',
      'Plugins',
      'Endpoints'
    ]) {
      // The rail scrolls when the window is short; bring each item in view.
      await tester.scrollUntilVisible(find.text(label), 40,
          scrollable: find.byType(Scrollable).first);
      expect(find.text(label), findsOneWidget);
    }
  });

  testWidgets('Navigation switches views and offline state names the command',
      (WidgetTester tester) async {
    await tester.pumpWidget(FlywheelApp(settings: DesktopSettings()));
    await tester.pump();
    // Offline (no gateway in the test environment): the Lanes view states
    // the fact and shows the command.
    expect(find.textContaining('flywheel up'), findsWidgets);
    // Switch to Receipts; its offline state renders too.
    await tester.tap(find.text('Receipts'));
    await tester.pump();
    expect(find.textContaining('receipts ledger'), findsOneWidget);
  });
}
