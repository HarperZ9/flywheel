import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/flywheel_nav.dart';

import 'journey_controller_test.dart';

Widget _journeyApp(
  ControllerHarness harness, {
  required bool alive,
  required VoidCallback onStartEngine,
  required void Function(DestinationId routeId) onGo,
  double width = 520,
  double height = 760,
}) =>
    MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SizedBox(
          width: width,
          height: height,
          child: FlywheelNav(
            goTo: (routeId, {arg}) => onGo(routeId),
            child: JourneyView(
              controller: harness.controller,
              alive: alive,
              onStartEngine: onStartEngine,
            ),
          ),
        ),
      ),
    );

void main() {
  testWidgets('empty Journey gives first-run routes instead of a dead end',
      (tester) async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    final opened = <DestinationId>[];
    var engineStarts = 0;

    await tester.pumpWidget(_journeyApp(
      harness,
      alive: false,
      onStartEngine: () => engineStarts++,
      onGo: opened.add,
    ));

    expect(find.text('No Journey projection was supplied.'), findsOneWidget);
    for (final label in const [
      'Start engine',
      'Models setup',
      'Projects',
      'Rowan',
      'Plan',
      'Code',
      'Receipts',
    ]) {
      expect(find.text(label), findsOneWidget, reason: label);
    }

    await tester.tap(find.widgetWithText(FilledButton, 'Start engine'));
    expect(engineStarts, 1);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Models setup'));
    expect(opened.last, DestinationId.models);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Projects'));
    expect(opened.last, DestinationId.projects);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Rowan'));
    expect(opened.last, DestinationId.chat);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Plan'));
    expect(opened.last, DestinationId.plan);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Code'));
    expect(opened.last, DestinationId.code);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Receipts'));
    expect(opened.last, DestinationId.receipts);
  });
}
