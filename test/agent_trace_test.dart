// The agent's process is a first-class object: the timeline renders each
// witnessed event the same way live and stored, a rescued emission is shown
// as a fact of the run, verdict pills come only from the engine's own
// checks, and a stored run that fails its content-address says TAMPERED.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/ide/agent_runs_panel.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/agent_timeline.dart';

Widget _wrap(Widget child) => MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  testWidgets('the timeline renders steps, tool verdicts, and the done pills',
      (tester) async {
    await tester.pumpWidget(_wrap(AgentTimeline(events: const [
      {'type': 'assistant', 'step': 1, 'text': 'reading the failing test'},
      {'type': 'tool_call', 'name': 'read', 'args': '{"path":"a.py"}'},
      {'type': 'tool_result', 'name': 'read', 'ok': true, 'output': 'def…'},
      {'type': 'tool_rescue', 'transform': 'unfenced-json'},
      {
        'type': 'done',
        'final': 'patched and green',
        'steps': 3,
        'verified': true,
        'integrity': {'clean': true},
      },
    ])));
    expect(find.text('reading the failing test'), findsOneWidget);
    expect(find.textContaining('⟲ rescued: unfenced-json'), findsOneWidget);
    expect(find.text('LEDGER VERIFIED'), findsOneWidget);
    expect(find.text('INTEGRITY CLEAN'), findsOneWidget);
    expect(find.text('patched and green'), findsOneWidget);
  });

  testWidgets('the runs list is a doorway: excerpt, intact pill, tap-through',
      (tester) async {
    Map<String, dynamic>? opened;
    await tester.pumpWidget(_wrap(AgentRunsList(
      runs: const [
        {
          'run_id': 'ab12cd34ef56ab12',
          'intact': true,
          'goal_excerpt': 'fix the failing parser test',
          'endpoint': 'serve',
          'steps': 4,
          'started': '2026-07-16T10:00:00',
        },
        {
          'run_id': 'ffffffffffffffff',
          'intact': false,
          'status': 'TAMPERED',
          'goal_excerpt': 'edited on disk',
          'endpoint': 'serve',
        },
      ],
      onOpen: (r) => opened = r,
    )));
    expect(find.text('fix the failing parser test'), findsOneWidget);
    expect(find.text('INTACT'), findsOneWidget);
    expect(find.text('TAMPERED'), findsOneWidget);
    await tester.tap(find.text('fix the failing parser test'));
    expect(opened?['run_id'], 'ab12cd34ef56ab12');
  });

  testWidgets('a stored run renders its trace and its content-address',
      (tester) async {
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: const {
      'run_id': 'ab12cd34ef56ab12',
      'intact': true,
      'goal_excerpt': 'fix the failing parser test',
      'final': 'patched and green',
      'steps': 2,
      'verified': true,
      'started': '2026-07-16T10:00:00',
      'events': [
        {'type': 'assistant', 'step': 1, 'text': 'the plan'},
        {'type': 'tool_result', 'name': 'run', 'ok': true, 'output': 'green'},
      ],
    })));
    expect(find.text('the plan'), findsOneWidget); // events replay verbatim
    expect(find.text('patched and green'), findsOneWidget); // done from doc
    expect(find.textContaining('ab12cd34ef56ab12'), findsOneWidget);
  });

  testWidgets('a tampered stored run says so before showing anything',
      (tester) async {
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: const {
      'run_id': 'ffffffffffffffff',
      'intact': false,
      'final': 'looks great',
      'events': [],
    })));
    expect(find.textContaining('TAMPERED'), findsOneWidget);
  });

  testWidgets('a stored run without events keeps the honest null',
      (tester) async {
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: const {
      'run_id': 'ab12cd34ef56ab12',
      'intact': true,
      'final': 'answered',
    })));
    expect(
        find.textContaining('No step events were stored'), findsOneWidget);
  });
}
