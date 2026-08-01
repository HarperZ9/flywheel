// Eval history and stored traces must stay honest at render time: a
// TAMPERED receipt reads as drift (a detected lie, never a neutral null),
// the intact pill only ever reflects the chain re-verification, verdict
// counts render as text (color stays a verdict), and every history row is
// a doorway to its full stored run.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/workflow_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/science_history.dart';
import 'package:flywheel_desktop/widgets/workflow_cards.dart';

Widget _wrap(Widget child) => MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  test('a TAMPERED workflow run or step reads as drift, not a null', () {
    final run = WorkflowRun.fromJson({
      'workflow': 'research-brief',
      'endpoint': 'serve',
      'status': 'TAMPERED',
      'chain_hash': 'abc',
      'steps': [
        {'name': 'draft', 'kind': 'agent', 'status': 'TAMPERED'}
      ],
    });
    expect(run.verdict, 'drift');
    expect(run.steps.first.verdict, 'drift');
  });

  testWidgets('science history renders the question and the intact pill',
      (tester) async {
    await tester.pumpWidget(_wrap(ScienceHistoryList(runs: [
      {
        'question': 'does the wrapper uplift small models',
        'chain_ok': true,
        'status': 'COMPLETE',
        'verdicts': {'UNVERIFIABLE': 1},
        'started': '2026-07-16T12:00:00',
        'chain_hash': 'ab12cd34ef56ab12',
      }
    ])));
    expect(find.text('does the wrapper uplift small models'), findsOneWidget);
    expect(find.text('INTACT'), findsOneWidget); // the pill voice is caps
    expect(find.textContaining('1 UNVERIFIABLE'), findsOneWidget);
  });

  testWidgets('a tampered science row says TAMPERED', (tester) async {
    await tester.pumpWidget(_wrap(ScienceHistoryList(runs: [
      {
        'question': 'q',
        'chain_ok': false,
        'status': 'TAMPERED',
        'verdicts': {'MATCH': 1},
        'chain_hash': 'ffff',
      }
    ])));
    expect(find.text('TAMPERED'), findsOneWidget);
    expect(find.text('INTACT'), findsNothing);
  });

  testWidgets('tapping a science history row opens the stored run',
      (tester) async {
    Map<String, dynamic>? opened;
    await tester.pumpWidget(_wrap(ScienceHistoryList(
      runs: [
        {'question': 'q1', 'chain_ok': true, 'chain_hash': 'aa11'},
      ],
      onOpen: (r) => opened = r,
    )));
    await tester.tap(find.text('q1'));
    expect(opened?['chain_hash'], 'aa11');
  });

  testWidgets('a past workflow run row is a doorway to its trace',
      (tester) async {
    var tapped = false;
    await tester.pumpWidget(_wrap(PastRunRow(
      run: const {
        'workflow': 'research-brief',
        'goal_excerpt': 'trace me',
        'endpoint': 'serve',
        'status': 'COMPLETED',
        'chain_hash': 'ab12',
      },
      onTap: () => tapped = true,
    )));
    await tester.tap(find.textContaining('trace me'));
    expect(tapped, isTrue);
  });
}
