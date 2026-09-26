import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/run_outcome.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_completion_summary.dart';
import 'package:flywheel_desktop/widgets/rowan_run_outcome_view.dart';

Map<String, dynamic> _projection() => (jsonDecode(File(
            '../tests/fixtures/gateway_run_outcome/stopped_projection.json')
        .readAsStringSync()) as Map<String, dynamic>)['projection']
    as Map<String, dynamic>;

Map<String, Object?> _item(String kind, String status, String? check,
        String detail) =>
    {'kind': kind, 'status': status, 'check': check, 'detail': detail};

RunCompletionOutcome _completion(List<Map<String, Object?>> items) {
  final counts = {
    for (final s in ['verified', 'claimed', 'failed'])
      s: items.where((i) => i['status'] == s).length
  };
  final verdict = counts['failed']! > 0
      ? 'failed'
      : counts['claimed']! > 0
          ? 'claimed'
          : 'verified';
  return RunCompletionOutcome.fromJson({
    'status': 'recorded',
    'verdict': verdict,
    'counts': counts,
    'items': items,
    'items_omitted': 0,
    'unbacked_success_claim': false,
  });
}

final _fileVerified = _item('file', 'verified', 'file_hash_recheck', 'matches');
final _answerClaimed = _item('final_answer', 'claimed', null, 'no_check_ran');
final _answerVerified = _item('final_answer', 'verified', 'test_command', 'passed');

Map<String, Object?> _outcome(List<Map<String, Object?>> items) => {
      'schema': runOutcomeSchema,
      'terminal_state': 'completed',
      'completion': {
        'status': 'recorded',
        'verdict': 'claimed',
        'counts': {'verified': 1, 'claimed': 1, 'failed': 0},
        'items': items,
        'items_omitted': 0,
        'unbacked_success_claim': true,
      },
      'budget': {'status': 'unrecorded'},
    };

void main() {
  test('the engine split parses from the shared projection', () {
    final projection = TraceProjection.fromJson(_projection(),
        operationRef: 'op_${'c' * 32}', journeyRef: 'jrn_${'b' * 32}');
    final completion = projection.runOutcome!.completion;
    expect(completion.verdict, 'failed');
    expect(completion.counts, {'verified': 1, 'claimed': 1, 'failed': 1});
    expect(completion.items.map(completionItemLine), [
      'File written: matches the hash recorded at write time.',
      'File written: claimed, no hash was recorded.',
      'Answer: the run did not complete (AGENT_RUN_BUDGET_EXHAUSTED).',
    ]);
  });

  test('done is said only when every deliverable passed a check', () {
    final claimed = _completion([_fileVerified, _answerClaimed]);
    expect(completionHeadline(claimed),
        'Finished, not verified: no check covered 1 of 2 deliverables.');
    expect(completionHeadline(claimed), isNot(contains('Done')));
    expect(claimed.done, isFalse);
    final verified = _completion([_fileVerified, _answerVerified]);
    expect(completionHeadline(verified), 'Done. Every deliverable passed a check.');
    final failed = _completion([
      _item('file', 'failed', 'file_hash_recheck', 'missing'),
      _answerVerified,
    ]);
    expect(completionHeadline(failed), 'Not done: 1 of 2 deliverables failed a check.');
    expect(completionSplit(failed), 'Verified 1 · Claimed 0 · Failed 1');
  });

  test('a split that contradicts its counts or its run is refused', () {
    expect(
        () => RunCompletionOutcome.fromJson({
              'status': 'recorded',
              'verdict': 'verified',
              'counts': {'verified': 1, 'claimed': 1, 'failed': 0},
              'items': [_fileVerified, _answerClaimed],
              'items_omitted': 0,
              'unbacked_success_claim': false,
            }),
        throwsFormatException);
    expect(
        () => RunCompletionOutcome.fromJson({
              'status': 'recorded',
              'verdict': 'claimed',
              'counts': {'verified': 0, 'claimed': 1, 'failed': 0},
              'items': [_item('final_answer', 'claimed', 'test_command', 'x')],
              'items_omitted': 0,
              'unbacked_success_claim': false,
            }),
        throwsFormatException);
    final failedRun = _outcome(
        [_fileVerified, _answerClaimed])
      ..['terminal_state'] = 'failed';
    (failedRun['completion'] as Map)['items'] = [_fileVerified, _answerVerified];
    (failedRun['completion'] as Map)['verdict'] = 'verified';
    (failedRun['completion'] as Map)['counts'] = {
      'verified': 2,
      'claimed': 0,
      'failed': 0
    };
    expect(() => RunOutcome.fromJson(failedRun, terminalState: 'failed'),
        throwsFormatException);
  });

  test('a file a command changed is named as claimed, never checked', () {
    final item = _completion([
      _item('file', 'claimed', null, 'changed_by_command'),
      _answerVerified,
    ]).items.first;
    expect(completionItemLine(item),
        'File changed by a command: claimed, nothing recorded what it holds.');
  });

  test('a check the step budget never reached is named as not run', () {
    final completion = _completion(
        [_fileVerified, _item('final_answer', 'failed', 'test_command', 'not_run')]);
    expect(completionItemLine(completion.items.last),
        'Answer: step budget exhausted; the test command never ran, so this is '
        'unwitnessed, not an observed failure.');
    expect(completionItemLine(completion.items.last),
        isNot(contains('did not pass')));
    expect(completionHeadline(completion),
        'Not done: the run stopped before it finished.');
  });

  testWidgets('the card leads with the split and never says done for claims',
      (tester) async {
    final outcome = RunOutcome.fromJson(
        _outcome([_fileVerified, _answerClaimed]),
        terminalState: 'completed');
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RowanRunOutcomeView(outcome: outcome))));
    expect(find.textContaining('Finished, not verified'), findsOneWidget);
    expect(find.textContaining('Done'), findsNothing);
    expect(find.text('Verified 1 · Claimed 1 · Failed 0'), findsOneWidget);
    expect(find.text(unbackedClaimLine), findsOneWidget);
    expect(find.textContaining('No budget record'), findsOneWidget);
  });
}
