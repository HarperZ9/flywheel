import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/flywheel_nav.dart';
import 'package:flywheel_desktop/widgets/start_task_prelude.dart';

import 'journey_controller_test.dart';

Widget _journeyApp(
  ControllerHarness harness, {
  required bool alive,
  required VoidCallback onStartEngine,
  required void Function(DestinationId routeId, Object? arg) onGo,
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
            goTo: (routeId, {arg}) => onGo(routeId, arg),
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
      onGo: (route, _) => opened.add(route),
    ));

    expect(find.text('No Journey projection was supplied.'), findsOneWidget);
    for (final label in const [
      'Start engine',
      'Start a task',
      'Models setup',
      'Projects',
      'Plan',
      'Code',
      'Receipts',
    ]) {
      expect(find.text(label), findsOneWidget, reason: label);
    }

    await _tapFilled(tester, 'Start engine');
    expect(engineStarts, 1);

    await _tapFilled(tester, 'Start a task');
    expect(opened.last, DestinationId.chat);
    await _tapOutlined(tester, 'Models setup');
    expect(opened.last, DestinationId.models);
    await _tapOutlined(tester, 'Projects');
    expect(opened.last, DestinationId.projects);
    await _tapOutlined(tester, 'Plan');
    expect(opened.last, DestinationId.plan);
    await _tapOutlined(tester, 'Code');
    expect(opened.last, DestinationId.code);
    await _tapOutlined(tester, 'Receipts');
    expect(opened.last, DestinationId.receipts);
  });

  testWidgets('Journey accepts a plain task before routing to Chat',
      (tester) async {
    final api = ScriptedJourneyApi();
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    DestinationId? opened;
    Object? handoff;

    await tester.pumpWidget(_journeyApp(
      harness,
      alive: true,
      onStartEngine: () {},
      onGo: (route, arg) {
        opened = route;
        handoff = arg;
      },
    ));

    await tester.enterText(find.byKey(const Key('journey-start-task-input')),
        'Find the receipts for the latest run.');
    await tester.pump();
    await tester.tap(find.byKey(const Key('journey-start-task-primary')));

    expect(opened, DestinationId.chat);
    expect(handoff, isA<StartTaskHandoff>());
    expect((handoff as StartTaskHandoff).text,
        'Find the receipts for the latest run.');
  });
}

Future<void> _tapFilled(WidgetTester tester, String label) async {
  final button = find.widgetWithText(FilledButton, label);
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
}

Future<void> _tapOutlined(WidgetTester tester, String label) async {
  final button = find.widgetWithText(OutlinedButton, label);
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
}
