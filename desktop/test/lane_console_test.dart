// lane_console_test.dart - one lane's tools, run from its card (WP9b).
//
// The console lists the tools under a plugin.probe approval, renders the
// chosen tool's form from its schema (a nested object included), sends one
// lane.call carrying the policy timeout and, above T1, the tier, waits the
// policy timeout plus 10 s. A tool this build leaves out is listed disabled
// with the engine's reason. The error codes are in lane_console_errors_test.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

import 'support/lane_console_fixture.dart';

void main() {
  testWidgets('listing asks for a plugin.probe approval naming the lane',
      (tester) async {
    final engine = LaneConsoleEngine();
    await pumpConsole(tester, engine);
    await listTools(tester);
    final probe = engine.operations.single;
    expect(probe.action, 'plugin.probe');
    expect(probe.destination, const GatewayDestination('plugin', 'crucible'));
    expect(engine.seen.single.url.path, '/api/lanes/crucible/tools');
    expect(lastCallBody(engine)['grant_ref'], 'gnt_test');
  });

  testWidgets('main tools come first; a tool not in the build is disabled',
      (tester) async {
    final engine = LaneConsoleEngine();
    await pumpConsole(tester, engine);
    await listTools(tester);
    final chips = tester
        .widgetList<ChoiceChip>(find.byType(ChoiceChip))
        .map((chip) => ((chip.label as Text).data, chip.onSelected != null))
        .toList();
    expect(chips, [
      ('crucible.assess (main)', true),
      ('crucible.run', true),
      ('crucible.status', true),
      ('crucible.refine', false),
    ]);
    expect(
        find.text('Not in this build (numpy_not_in_build).'), findsOneWidget);
  });

  testWidgets(
      'the form renders a nested object and the call carries the policy '
      'timeout', (tester) async {
    final engine = LaneConsoleEngine();
    await pumpConsole(tester, engine);
    await listTools(tester);
    await chooseTool(tester, 'crucible.assess (main)');
    expect(find.text('OBJECT'), findsOneWidget);
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), r'C:\work\thesis.md');
    await tester.enterText(fields.at(1), '{"strict": true}');
    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    final call = engine.operations.last;
    expect(call.action, 'lane.call');
    expect(call.destination, const GatewayDestination('lane', 'crucible'));
    expect(call.operation['timeout'], 30);
    expect(call.operation.containsKey('governance_tier'), isFalse);
    expect(engine.seen.last.url.path, '/api/lane/crucible/crucible.assess');
    final sent = lastCallBody(engine);
    expect(sent['args'], {
      'thesis': r'C:\work\thesis.md',
      'options': {'strict': true}
    });
    expect(sent['timeout'], 30);
    expect(find.text('claims'), findsOneWidget);
    expect(find.text('3 items'), findsOneWidget);
    expect(find.text('Raw JSON'), findsOneWidget);
  });

  testWidgets('a required field left empty sends nothing', (tester) async {
    final engine = LaneConsoleEngine();
    await pumpConsole(tester, engine);
    await listTools(tester);
    await chooseTool(tester, 'crucible.assess (main)');
    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    expect(find.text('Fill the required fields: thesis.'), findsOneWidget);
    expect(engine.operations.map((o) => o.action), ['plugin.probe']);
  });

  testWidgets('a T2 tool sends its tier in the approval', (tester) async {
    final engine = LaneConsoleEngine();
    await pumpConsole(tester, engine);
    await listTools(tester);
    await chooseTool(tester, 'crucible.run');
    expect(find.textContaining('T2: the approval names this tier.'),
        findsOneWidget);
    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    expect(engine.operations.last.operation['governance_tier'], 'T2');
    expect(engine.operations.last.operation['timeout'], 120);
  });

  testWidgets('the app waits the policy timeout plus 10 s', (tester) async {
    final engine = LaneConsoleEngine()..callDelay = const Duration(seconds: 35);
    await pumpConsole(tester, engine);
    await listTools(tester);
    await chooseTool(tester, 'crucible.status');
    await tester.tap(find.text('Run'));
    await tester.pump(const Duration(seconds: 31));
    // crucible.status: 20 s policy, so the app stops waiting at 30 s.
    expect(
        find.text('No answer reached the app within 30 s. '
            'The engine may still finish the call.'),
        findsOneWidget);
    await tester.pump(const Duration(seconds: 10));

    await chooseTool(tester, 'crucible.assess (main)');
    await tester.enterText(find.byType(TextField).at(0), 'thesis.md');
    await tester.tap(find.text('Run'));
    await tester.pump(const Duration(seconds: 36));
    // crucible.assess: 30 s policy, so a 35 s answer still arrives.
    expect(find.text('verdict'), findsOneWidget);
    expect(find.textContaining('No answer reached the app'), findsNothing);
  });
}
