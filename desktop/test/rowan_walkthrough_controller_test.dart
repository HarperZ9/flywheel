import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/controllers/rowan_walkthrough_controller.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
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
  test('read-only scenario builds one supervised agent.run operation', () {
    final controller = RowanWalkthroughController(
        scenario: rowanRetryPolicyWalkthroughScenario);
    addTearDown(controller.dispose);

    controller
      ..selectEndpoint('ollama')
      ..selectModel('qwen2.5-coder-14b-instruct')
      ..setRoot(r'C:\synthetic\repo');

    final operation = controller.operationFor('walkthrough-1');

    expect(operation, isNotNull);
    expect(operation!.action, 'agent.run');
    expect(operation.tool, 'agent.run');
    expect(
        operation.destination, const GatewayDestination('endpoint', 'ollama'));
    expect(operation.scopes, ['network']);
    expect(operation.operation['goal'], contains('Review the retry policy'));
    expect(operation.operation['endpoint'], 'ollama');
    expect(operation.operation['model'], 'qwen2.5-coder-14b-instruct');
    expect(operation.operation['root'], r'C:\synthetic\repo');
    expect(operation.operation['allow_write'], isFalse);
    expect(operation.operation['allow_exec'], isFalse);
    expect(operation.operation['stream'], isTrue);
    expect(operation.operation['max_steps'], 3);
    expect(operation.operation['max_tokens'], 1024);
    expect(operation.operation['timeout_s'], 300);
    expect(operation.operation['data_refs'], <String>[]);
    expect(operation.operation['credential_refs'], <String>[]);
    expect(operation.operation.containsKey('oracle'), isFalse);
    expect(operation.operation.containsKey('expected_defect'), isFalse);
  });

  test('denied approval records an outcome without advancing execution', () {
    final controller = RowanWalkthroughController(
        scenario: rowanRetryPolicyWalkthroughScenario);
    addTearDown(controller.dispose);

    controller
      ..selectEndpoint('ollama')
      ..setRoot(r'C:\synthetic\repo')
      ..markReviewPrepared();
    controller.markDenied();

    expect(controller.checkpoint, RowanWalkthroughCheckpoint.review);
    expect(controller.outcome, RowanWalkthroughOutcome.denied);
    expect(controller.snapshot, isNull);
    expect(controller.events, isEmpty);
  });

  test('semantic oracle and reopen are separate gates', () {
    final controller = RowanWalkthroughController(
        scenario: rowanRetryPolicyWalkthroughScenario);
    addTearDown(controller.dispose);

    controller
      ..selectEndpoint('ollama')
      ..setRoot(r'C:\synthetic\repo');
    controller.acceptSnapshot(_snapshot('running', canCancel: true));
    controller.acceptTerminalResult(_result('The function looks fine.'));
    controller.markReopened(_snapshot('completed',
        head: _headB, resultSha256: _digest('The function looks fine.')));

    expect(controller.oracle.state, RowanWalkthroughOracleState.failed);
    expect(controller.canPrepareFollowUp, isFalse);
    expect(controller.checkpoint, RowanWalkthroughCheckpoint.semanticOracle);

    controller.acceptTerminalResult(_result(
        'Line 6 has an off-by-one bug: next_attempt <= max_attempts + 1 '
        'allows attempt 4 when max_attempts is 3. It should require '
        'next_attempt <= max_attempts.'));
    expect(controller.oracle.state, RowanWalkthroughOracleState.passed);
    expect(controller.canPrepareFollowUp, isFalse);

    controller.markReopened(_snapshot('completed',
        head: _headB,
        resultSha256: _digest(
            'Line 6 has an off-by-one bug: next_attempt <= max_attempts + 1 '
            'allows attempt 4 when max_attempts is 3. It should require '
            'next_attempt <= max_attempts.')));
    expect(controller.checkpoint, RowanWalkthroughCheckpoint.reopened);
    expect(controller.canPrepareFollowUp, isTrue);
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
