import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:crypto/crypto.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _headC =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';

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
  _reviewTerminalResultTest();
  _reviewCancelRaceTest();
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

    final canonical = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {
        '\u{E000}': 1,
        '\u{10000}': 2,
        'small': 1e-5,
        'large': 1e20,
        'tiny': 1e-7,
      },
    });
    expect(canonical.canonicalSha256,
        '1dce483b3a485d2fcf2ab59b284ea7fd12b3d1822869109de58710e4790c93a8');
  });
}

void _reviewTerminalResultTest() {
  test('review W12 typed terminal result precedes one terminal callback',
      () async {
    final result = <String, Object?>{
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {'final': 'answer'},
    };
    final canonical = '{"action":"agent.run","operation_ref":"$_operation",'
        '"result":{"final":"answer"},"schema":"flywheel.gateway-operation-result/v1",'
        '"state":"completed"}';
    final digest = sha256.convert(utf8.encode(canonical)).toString();
    final terminal =
        _snapshot('completed', head: _headB, terminal: _headC, result: digest);
    final wire = 'id: 1\nevent: terminal\ndata: ${jsonEncode({
          'snapshot': terminal,
          'result': result
        })}\n\n';
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((_) async => http.Response(wire, 200)));
    final notified = Completer<void>();
    OperationResult? received;
    var calls = 0;
    final controller = Function.apply(OperationController.new, const [], {
      #requestId: () => 'stop-1',
      #onTerminalResult: (OperationResult value) {
        calls++;
        received = value;
        if (!notified.isCompleted) notified.complete();
      }
    }) as OperationController;
    controller.observe(GatewayOperations(client).start(const {}),
        onProgress: (_) {}, onInterrupted: () {});
    await notified.future.timeout(const Duration(seconds: 1));
    expect((controller as dynamic).terminalResult, same(received));
    expect(received?.result, {'final': 'answer'});
    expect(calls, 1);
    controller.dispose();
    client.close();
  });
}

void _reviewCancelRaceTest() {
  test('review W13 cancel response never outruns authoritative SSE order', () {
    final running =
        OperationSnapshot.fromJson(_snapshot('running', canCancel: true));
    final stopping =
        OperationSnapshot.fromJson(_snapshot('cancel_requested', head: _headB));
    final cancelled = OperationSnapshot.fromJson(
        _snapshot('cancelled', head: _headC, terminal: _headC, result: _headB));

    final responseFirst = OperationController(requestId: () => 'stop-1');
    responseFirst.acceptSnapshot(running);
    expect((responseFirst as dynamic).acceptCancelResponse(cancelled), isTrue);
    expect(responseFirst.execution?.state, OperationState.running);
    expect(responseFirst.acceptSnapshot(stopping), isTrue);

    final sseFirst = OperationController(requestId: () => 'stop-2');
    sseFirst.acceptSnapshot(running);
    expect(sseFirst.acceptSnapshot(stopping), isTrue);
    expect((sseFirst as dynamic).acceptCancelResponse(cancelled), isTrue);
    expect(sseFirst.execution?.state, OperationState.cancelRequested);
    responseFirst.dispose();
    sseFirst.dispose();
  });
}
