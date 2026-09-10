import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/agent_runs_panel.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/agent_timeline.dart';

Widget wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Future<void> openDetails(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(TextButton, 'Details').first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
      'long failed output is selectable through its last line on replay',
      (tester) async {
    final output =
        '${List.generate(100, (i) => 'line $i').join('\n')}\nFAILED: final source row';
    final event = {
      'type': 'tool_result',
      'name': 'query',
      'ok': false,
      'output': output
    };
    await tester.pumpWidget(wrap(StoredAgentRun(doc: {
      'intact': true,
      'run_id': 'fixture',
      'events': [event],
    })));
    await openDetails(tester);
    expect(find.text('Execution failed'), findsWidgets);
    final fullOutput =
        find.byWidgetPredicate((w) => w is SelectableText && w.data == output);
    expect(fullOutput, findsOneWidget);
    final scroll = find
        .descendant(of: find.byType(Dialog), matching: find.byType(Scrollable))
        .first;
    await tester.fling(scroll, const Offset(0, -5000), 5000);
    await tester.pumpAndSettle();
    final position = tester.state<ScrollableState>(scroll).position;
    expect(position.maxScrollExtent, greaterThan(0));
    expect(position.extentAfter, 0);
    final editable = tester.widget<EditableText>(
        find.descendant(of: fullOutput, matching: find.byType(EditableText)));
    expect(editable.maxLines, isNull);
    final render = tester
        .state<EditableTextState>(find.descendant(
            of: fullOutput, matching: find.byType(EditableText)))
        .renderEditable;
    final caret = render.localToGlobal(render
        .getLocalRectForCaret(TextPosition(offset: output.length))
        .center);
    expect(tester.getRect(find.byType(Dialog)).contains(caret), isTrue);
    expect(tester.takeException(), isNull);
    expect(event['output'], output);
    expect(find.textContaining('does not establish factual accuracy'),
        findsOneWidget);
  });

  testWidgets('unknown typed event preserves JSON source selector and values',
      (tester) async {
    final payload = {
      'source': 'invoice.json',
      'pointer': '/rows/0/net~1amount',
      'lines': [21, 24],
      'value': 4169,
      'unit': 'USD',
      'present': false,
    };
    final event = {
      'type': 'source_observation',
      'payload': payload,
      'truncated': true,
      'original_chars': 2048,
    };
    final before = jsonEncode(event);
    await tester.pumpWidget(wrap(AgentTimeline(events: [event])));
    expect(find.text('Event: source_observation'), findsOneWidget);
    await openDetails(tester);
    expect(find.text('Full recorded payload'), findsOneWidget);
    expect(find.text('payload (object)'), findsOneWidget);
    expect(find.text('truncated (boolean)'), findsOneWidget);
    expect(find.text('original_chars (number)'), findsOneWidget);
    expect(find.text('2048'), findsOneWidget);
    final jsonText = tester
        .widgetList<SelectableText>(find.byType(SelectableText))
        .map((w) => w.data)
        .whereType<String>()
        .firstWhere((s) => s.contains('net~1amount'));
    expect(jsonDecode(jsonText), payload);
    expect(jsonEncode(event), before);
  });

  testWidgets(
      'narrow view supports keyboard opening and escape with missing data',
      (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(wrap(const AgentTimeline(events: [
      {'type': 'tool_result', 'name': 'query'},
    ])));
    expect(find.text('Execution status unavailable'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.text('output: not recorded'), findsOneWidget);
    expect(find.text('ok: not recorded'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsNothing);
  });

  testWidgets('tool arguments remain original text including line endings',
      (tester) async {
    const args = '{\r\n  "pointer": "/rows/3",\r\n  "value": "004169"\r\n}';
    await tester.pumpWidget(wrap(const AgentTimeline(events: [
      {'type': 'tool_call', 'name': 'read', 'args': args},
    ])));
    await openDetails(tester);
    expect(find.byWidgetPredicate((w) => w is SelectableText && w.data == args),
        findsOneWidget);
    expect(find.text('args (string)'), findsOneWidget);
  });
}
