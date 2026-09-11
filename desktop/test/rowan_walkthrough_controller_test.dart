import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/controllers/rowan_walkthrough_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/rowan_walkthrough_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _event =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';

void main() {
  test('denied approval records an outcome without lifecycle state', () {
    final controller = RowanWalkthroughController(
        scenario: rowanRetryPolicyWalkthroughScenario);
    addTearDown(controller.dispose);

    controller.markReviewPrepared();
    controller.markDenied();

    expect(controller.checkpoint, RowanWalkthroughCheckpoint.review);
    expect(controller.outcome, RowanWalkthroughOutcome.denied);
    expect(controller.terminalOperationRef, isNull);
    expect(controller.terminalResultSha256, isNull);
  });

  test('semantic oracle and reopen are separate gates', () {
    final controller = RowanWalkthroughController(
        scenario: rowanRetryPolicyWalkthroughScenario);
    addTearDown(controller.dispose);

    controller.acceptTerminalResult(_result('The function looks fine.'),
        snapshot: _snapshot('completed',
            head: _headA, resultSha256: _digest('The function looks fine.')));
    controller.markReopened(_snapshot('completed',
        head: _headB, resultSha256: _digest('The function looks fine.')));

    expect(controller.oracle.state, RowanWalkthroughOracleState.failed);
    expect(controller.canPrepareFollowUp, isFalse);
    expect(controller.checkpoint, RowanWalkthroughCheckpoint.semanticOracle);
    expect(controller.outcome, RowanWalkthroughOutcome.wrongAnswer);

    const accepted =
        'Line 6 has an off-by-one bug: next_attempt <= max_attempts + 1 '
        'allows attempt 4 when max_attempts is 3. It should require '
        'next_attempt <= max_attempts.';
    final result = _result(accepted);
    controller.acceptTerminalResult(result,
        snapshot: _snapshot('completed',
            head: _headA, resultSha256: result.canonicalSha256));

    expect(controller.oracle.state, RowanWalkthroughOracleState.passed);
    expect(controller.canPrepareFollowUp, isFalse);
    expect(controller.terminalOperationRef, _operation);
    expect(controller.terminalResultSha256, result.canonicalSha256);

    controller.markReopened(_snapshot('completed',
        head: _headB, resultSha256: result.canonicalSha256));
    expect(controller.checkpoint, RowanWalkthroughCheckpoint.reopened);
    expect(controller.canPrepareFollowUp, isTrue);
    expect(controller.lastJourneyRef, _journey);
    expect(controller.lastEventHeadSha256, _headB);
  });

  test('oracle labels missing final answers unavailable', () {
    final oracle = rowanRetryPolicyWalkthroughScenario.evaluate(const {});

    expect(oracle.state, RowanWalkthroughOracleState.unavailable);
    expect(oracle.message, contains('readable final answer'));
  });
}

OperationSnapshot _snapshot(String state,
        {String head = _headA, bool canCancel = false, String? resultSha256}) =>
    OperationSnapshot.fromJson({
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': state == 'completed' ? _event : null,
      'result_sha256':
          state == 'completed' ? resultSha256 ?? _digest('done') : null,
    });

OperationResult _result(String finalText) => OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {'final': finalText},
    });

String _digest(String finalText) => sha256
    .convert(utf8.encode(jsonEncode({
      'action': 'agent.run',
      'operation_ref': _operation,
      'result': {'final': finalText},
      'schema': operationResultSchema,
      'state': 'completed',
    })))
    .toString();
