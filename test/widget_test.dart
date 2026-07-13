// A basic smoke test: the app builds and shows the Flywheel shell.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/main.dart';

void main() {
  testWidgets('App renders the Flywheel shell', (WidgetTester tester) async {
    await tester.pumpWidget(const FlywheelApp());
    await tester.pump();
    expect(find.text('Flywheel'), findsWidgets);
    expect(find.byType(NavigationRail), findsOneWidget);
  });
}
