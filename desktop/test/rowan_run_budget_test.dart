import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';
import 'package:flywheel_desktop/models/rowan_run_budget.dart';
import 'package:flywheel_desktop/models/run_outcome.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_run_outcome_view.dart';

Map<String, dynamic> _fixture() => (jsonDecode(File(
            '../tests/fixtures/gateway_run_outcome/stopped_projection.json')
        .readAsStringSync()) as Map<String, dynamic>)['projection']
    as Map<String, dynamic>;

TraceProjection _parse(Map<String, dynamic> value) => TraceProjection.fromJson(
    value,
    operationRef: 'op_${'c' * 32}',
    journeyRef: 'jrn_${'b' * 32}');

Map<String, dynamic> _rehash(Map<String, dynamic> value) {
  final body = Map<String, dynamic>.from(value)..remove('projection_sha256');
  return {...body, 'projection_sha256': canonicalJsonSha256(body)};
}

void main() {
  test('the engine projection parses with the hash Python computed', () {
    final projection = _parse(_fixture());
    final budget = projection.runOutcome!.budget;
    expect(projection.reason, 'AGENT_RUN_BUDGET_EXHAUSTED');
    expect(budget.status, 'stopped');
    expect(budget.tripped, 'tool_actions');
    expect(budget.used['tool_actions'], 24);
    expect(budget.falseSuccessSignals, ['rate_limit']);
  });

  test('an unknown field or a forged stop makes the projection invalid', () {
    final extra = _fixture();
    (extra['run_outcome'] as Map)['budget']['surprise'] = 1;
    expect(() => _parse(_rehash(extra)), throwsFormatException);
    final forged = _fixture();
    (forged['run_outcome'] as Map)['budget']['status'] = 'within_limits';
    expect(() => _parse(_rehash(forged)), throwsFormatException);
    final unhashed = _fixture();
    (unhashed['run_outcome'] as Map)['budget']['used']['tool_actions'] = 3;
    expect(() => _parse(unhashed), throwsFormatException);
  });

  test('the summary names the limit and never guesses unreported spend', () {
    final budget = _parse(_fixture()).runOutcome!.budget;
    expect(budgetHeadline(budget),
        'Stopped by the run budget: tool action limit reached (24 of 24).');
    expect(budgetSpendLine(budget),
        contains('spend not reported by the provider'));
    expect(budgetSpendLine(budget), contains('12,400 of 200,000 tokens'));
    // The harness's check runs are listed apart from the model's tool actions.
    expect(budget.harnessChecks, 1);
    expect(budgetSpendLine(budget),
        contains('24 of 24 tool actions · 1 check command run'));
    expect(
        falseSuccessLine(budget),
        '1 success report from the provider or the CLI came with a rate limit '
        'error.');
    expect(budget.limitSignalSteps.single.match, 'rate_limit_error');
    expect(budget.limitSignalSteps.single.tool, 'provider');
    final unverifiable = RunBudgetOutcome.fromJson({
      'status': 'unverifiable',
      'reason': 'BUDGET_UNDERCOUNTS_TRACE',
      'record_sequence': 3,
    });
    expect(budgetHeadline(unverifiable), startsWith('Budget record unverifiable'));
  });

  test('a CLI session whose messages streamed usage shows the spend it reported',
      () {
    // The engine derives this block from a Claude CLI session's events
    // (tests/test_rowan_run_budget_mirror.py). Its cost arrives only in the
    // result event and covers every model call in the session.
    final data = jsonDecode(File(
                '../tests/fixtures/gateway_run_outcome/cli_streamed_spend.json')
            .readAsStringSync()) as Map<String, dynamic>;
    final budget =
        RunBudgetOutcome.fromJson(data['budget'] as Map<String, dynamic>);
    expect(budgetHeadline(budget),
        'Stopped by the run budget: spend limit reached (\$4.25 of \$2.00).');
    expect(budgetSpendLine(budget), contains('spend \$4.25 of \$2.00'));
    expect(budgetSpendLine(budget), isNot(contains('not reported')));
  });

  testWidgets('the card view shows a stop as an honest null', (tester) async {
    final projection = _parse(_fixture());
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: RowanRunOutcomeView(
              outcome: projection.runOutcome!, reason: projection.reason)),
    ));
    expect(find.textContaining('tool action limit reached (24 of 24)'),
        findsOneWidget);
    expect(find.textContaining('from the provider or the CLI came with a rate limit'),
        findsOneWidget);
    // A tool-action stop does not list limit-signal steps.
    expect(find.byKey(const Key('rowan-limit-signal-step')), findsNothing);
  });

  testWidgets('a limit-signal stop names each counted step and its words',
      (tester) async {
    final raw = Map<String, dynamic>.from(
        (_fixture()['run_outcome'] as Map)['budget'] as Map);
    raw['tripped'] = 'limit_signals';
    raw['limit_signal_steps'] = [
      for (final match in ['status 429', 'rate_limit_error'])
        {'tool': 'provider', 'signal': 'rate_limit', 'match': match},
    ];
    final budget = RunBudgetOutcome.fromJson(raw);
    expect(budgetHeadline(budget),
        'Stopped by the run budget: 2 limit errors in a row from the provider '
        'or the CLI.');
    expect(limitSignalLines(budget), [
      'provider: rate limit, matched "status 429"',
      'provider: rate limit, matched "rate_limit_error"',
    ]);
    expect(limitSignalLines(budget, reason: 'AGENT_FALSE_SUCCESS'), hasLength(2));
    raw['limit_signal_steps'] = [
      {'tool': 'run', 'signal': 'rate_limit', 'match': ''},
    ];
    expect(() => RunBudgetOutcome.fromJson(raw), throwsFormatException);
    final full = Map<String, dynamic>.from(
        (_fixture()['run_outcome'] as Map)['budget'] as Map)
      ..remove('limit_signal_steps');
    expect(() => RunBudgetOutcome.fromJson(full), throwsFormatException);
  });

  test('only the limits the owner set travel, and bad ones are refused', () {
    const unset = RowanRunBudget();
    expect(unset.toWire(), isNull);
    final set = unset.withToolActions(5).withCostMicros(500000);
    expect(set.toWire(), {'max_tool_actions': 5, 'max_cost_micros': 500000});
    expect(unset.withToolActions(201).invalidField, 'max_tool_actions');
    expect(costMicrosFromDollars(r'$1.25'), 1250000);
    expect(costMicrosFromDollars(''), isNull);
    final rowan = RowanOperationController(GatewayClient());
    addTearDown(rowan.dispose);
    rowan.setRunBudget(unset.withUsageTokens(10));
    expect(rowan.error, 'INVALID_RUN_BUDGET');
    expect(rowan.runBudget, unset);
  });

  testWidgets('an owner override is part of the operation sent for approval',
      (tester) async {
    Map<String, Object?>? approved;
    final rowan = RowanOperationController(GatewayClient())
      ..setEndpoint('local')
      ..setRunBudget(const RowanRunBudget(maxToolActions: 3));
    addTearDown(rowan.dispose);
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      home: GatewayOperationScope(
        authorize: (_, operation, supplier, dispatch) async {
          approved = operation.operation;
          return const GatewayAuthorizationOutcome<bool>.denied();
        },
        child: Builder(builder: (ctx) {
          context = ctx;
          return const SizedBox.shrink();
        }),
      ),
    ));
    await rowan.start(context, 'inspect');
    expect(approved?['run_budget'], {'max_tool_actions': 3});
    expect(approved?.containsKey('test_cmd'), isFalse);

    // A check command travels only with exec allowed, since the engine runs
    // it through the exec gate; with exec off it would fail every run.
    rowan.setCheckCommand('python -m pytest -q');
    await rowan.start(context, 'inspect');
    expect(approved?.containsKey('test_cmd'), isFalse);
    rowan.setAllowExec(true);
    await rowan.start(context, 'inspect');
    expect(approved?['test_cmd'], 'python -m pytest -q');
  });
}
