import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/controllers/operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, Object?> _snapshot(String state,
        {String head = _headA,
        bool canCancel = false,
        String? terminal,
        String? result}) =>
    {
      'schema': 'flywheel.gateway-operation-snapshot/v1',
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': terminal,
      'result_sha256': result,
    };

void main() {
  _snapshotTests();
  _controllerTests();
  _resultTests();
}

void _snapshotTests() {
  test('snapshot parser enforces exact schema fields and state invariants', () {
    final running =
        OperationSnapshot.fromJson(_snapshot('running', canCancel: true));
    expect((running.state, running.canCancel, running.isTerminal),
        (OperationState.running, true, false));
    final unowned = OperationSnapshot.fromJson(_snapshot('running'));
    expect((unowned.state, unowned.canCancel), (OperationState.running, false));

    for (final invalid in <Map<String, Object?>>[
      {..._snapshot('running', canCancel: true), 'extra': true},
      _snapshot('unknown'),
      _snapshot('queued', canCancel: true),
      _snapshot('completed', canCancel: true),
      _snapshot('completed'),
      _snapshot('completed', terminal: 'evt_bad', result: _headA),
    ]) {
      expect(() => OperationSnapshot.fromJson(invalid), throwsArgumentError);
    }
  });
}

void _controllerTests() {
  test('controller accepts replay and forward state but fails closed on drift',
      () {
    final controller = OperationController(requestId: () => 'stop-1');
    final running =
        OperationSnapshot.fromJson(_snapshot('running', canCancel: true));
    expect(controller.acceptSnapshot(running), isTrue);
    expect(controller.acceptSnapshot(running), isTrue);

    final changedSameState = OperationSnapshot.fromJson(
        _snapshot('running', head: _headB, canCancel: true));
    expect(controller.acceptSnapshot(changedSameState), isFalse);
    expect(controller.observerState, OperationObserverState.error);
    expect(controller.execution, same(running));

    controller.dispose();
  });

  test('observer closure and failure never manufacture execution terminal', () {
    final controller = OperationController(requestId: () => 'stop-1');
    final running =
        OperationSnapshot.fromJson(_snapshot('running', canCancel: true));
    controller.beginObservation();
    controller.acceptSnapshot(running);
    controller.closeObservation();
    expect(controller.observerState, OperationObserverState.closed);
    expect(controller.execution?.state, OperationState.running);

    controller.beginObservation();
    controller.failObservation();
    expect(controller.observerState, OperationObserverState.error);
    expect(controller.execution?.state, OperationState.running);
    controller.dispose();
  });
}

void _resultTests() {
  test('terminal result is exact, bounded, and deeply immutable', () {
    final raw = <String, Object?>{
      'nested': <String, Object?>{'value': 1}
    };
    final result = OperationResult.fromJson({
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': raw,
    });
    (raw['nested'] as Map<String, Object?>)['value'] = 2;

    expect(result.result, {
      'nested': {'value': 1}
    });
    expect(() => result.result['extra'] = true, throwsUnsupportedError);
    expect(() => (result.result['nested'] as Map<String, Object?>)['value'] = 3,
        throwsUnsupportedError);
    expect(
        () => OperationResult.fromJson({
              'schema': 'flywheel.gateway-operation-result/v1',
              'operation_ref': _operation,
              'action': 'plugin.call',
              'state': 'completed',
              'result': const {},
            }),
        throwsArgumentError);
  });
}
