// companion_effort_test.dart -- the companion answer, its receipt, and the
// dial that governs it.
//
// The model declared `receipt` as a String while the engine has always sent an
// object, so every real answer threw inside fromJson and the Companion
// destination could not render one at all. The parse defect and the dial that
// depends on it are held here together, because the dial is only honest if the
// stamp it produces survives the trip back.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/companion_receipt_strip.dart';
import 'package:flywheel_desktop/widgets/effort_dial.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

/// What harness/companion.py actually returns: the selection receipt as an
/// object, with the effort stamp nested inside it.
const _engineAnswer = {
  'source': 'local-verified',
  'text': 'the answer',
  'escalate_to': null,
  'best_effort_text': null,
  'receipt': {
    'schema': 'flywheel.selection-receipt/v1',
    'method': 'oracle',
    'selected_index': 2,
    'confidence': 0.8125,
    'candidates_used': 8,
    'battery_hash': 'b8d2f0a1c3e45567',
    'verdict': 'PASS',
    'reason': 'oracle accepted candidate 2',
    'effort': {
      'name': 'high',
      'applied': 'candidates',
      'initial_n': 8,
      'max_n': 32,
      'initial_n_applied': 8,
      'max_n_applied': 32,
      'max_n_overridden': false,
      'candidates_generated': 8,
      'n_candidates_applied': true,
    },
  },
};

void main() {
  test('an engine-shaped answer parses instead of throwing', () {
    // The regression. Before this, `type _Map is not a subtype of String?`
    // fired on every answer the engine ever produced, including an empty one.
    final r =
        CompanionResult.fromJson(Map<String, dynamic>.from(_engineAnswer));
    expect(r.source, 'local-verified');
    expect(r.text, 'the answer');
    expect(r.receipt, isA<Map<String, dynamic>>());
    expect(r.receipt!['candidates_used'], 8);
  });

  test('the verdict is read from the receipt that carries it', () {
    // The engine puts the verdict inside the receipt and never at the top
    // level, so reading only the top level left every answer's chip on its
    // fallback color while a real verdict sat one level down.
    final r =
        CompanionResult.fromJson(Map<String, dynamic>.from(_engineAnswer));
    expect(r.verdict, 'PASS');
  });

  test('a receipt of the wrong shape degrades instead of crashing', () {
    // A gateway-facing model degrades on a missing or unexpected field. The
    // string case is the shape the model used to insist on.
    final r = CompanionResult.fromJson({
      'source': 'escalate',
      'receipt': 'deadbeef',
      'text': 42,
    });
    expect(r.receipt, isNull);
    expect(r.text, isNull);
    expect(r.verdict, isNull);
    expect(r.escalated, isTrue);
  });

  test('the effort stamp is reachable from the answer', () {
    final r =
        CompanionResult.fromJson(Map<String, dynamic>.from(_engineAnswer));
    expect(r.effort!['name'], 'high');
    expect(r.effort!['candidates_generated'], 8);
  });

  test('ultra separates from high on candidates, not on steps', () {
    // The reason this surface shows candidates. On steps the two levels are
    // identical, so a step reading would tell the operator that raising the
    // dial bought nothing, which is false for a selection loop.
    expect(EffortLevel.ultra.maxSteps, EffortLevel.high.maxSteps);
    expect(EffortLevel.ultra.maxN, greaterThan(EffortLevel.high.maxN));
  });

  test('the dial mirrors the engine candidate table', () {
    // harness/effort.py CANDIDATE_BUDGET. standard matches the seat's
    // constructed default, so the middle position and no dial at all agree.
    expect(
      {
        for (final l in EffortLevel.values) l.wire: [l.initialN, l.maxN]
      },
      {
        'low': [1, 4],
        'standard': [4, 16],
        'high': [8, 32],
        'ultra': [16, 64],
      },
    );
  });

  testWidgets('the candidate budget is shown where candidates are spent',
      (tester) async {
    await tester.pumpWidget(_wrap(EffortDial(
      value: EffortLevel.ultra,
      consequence: EffortConsequence.candidates,
      onChanged: (_) {},
    )));
    expect(find.text('64 candidates'), findsOneWidget);
    expect(find.text('12 steps'), findsNothing);
  });

  testWidgets('the strip reports what the dial actually bought',
      (tester) async {
    final r =
        CompanionResult.fromJson(Map<String, dynamic>.from(_engineAnswer));
    await tester.pumpWidget(_wrap(CompanionReceiptStrip(r.receipt)));
    expect(find.text('high · 8 of 32 candidates'), findsOneWidget);
    expect(find.text('effort'), findsOneWidget);
    expect(find.text('oracle'), findsOneWidget);
    expect(find.text('8'), findsOneWidget, reason: 'candidates used');
  });

  testWidgets('a dial that went unspent says so rather than claiming a budget',
      (tester) async {
    // A proof-cache hit answers before the loop runs. Reporting the level's
    // budget there would describe generations that never happened.
    await tester.pumpWidget(_wrap(const CompanionReceiptStrip({
      'method': 'cache',
      'effort': {
        'name': 'ultra',
        'applied': 'none',
        'candidates_generated': 0,
        'n_candidates_applied': false,
        'reason': 'answered from the proof cache; no candidates generated',
      },
    })));
    expect(
        find.text('ultra · answered from the proof cache; '
            'no candidates generated'),
        findsOneWidget);
  });

  testWidgets('an empty or absent receipt renders nothing at all',
      (tester) async {
    await tester.pumpWidget(_wrap(const Column(children: [
      CompanionReceiptStrip(null),
      CompanionReceiptStrip({}),
      CompanionReceiptStrip({'schema': 'flywheel.selection-receipt/v1'}),
    ])));
    expect(find.byType(Wrap), findsNothing);
  });

  test('the dial travels in the grant the operator approves', () {
    // The budget is part of what is being authorized. Sending it outside the
    // approved operation would let the sheet show one spend and the dispatch
    // make another.
    final op =
        GatewayOperation.companionAsk('request-1', 'a prompt', effort: 'ultra');
    expect(op.operation['effort'], 'ultra');
    expect(op.action, 'companion.ask');
  });

  test('no dial sends no field, which is not the same as sending standard', () {
    final op = GatewayOperation.companionAsk('request-1', 'a prompt');
    expect(op.operation.containsKey('effort'), isFalse);
  });
}
