import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:crypto/crypto.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_sse_decoder.dart';
import 'package:flywheel_desktop/controllers/operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/widgets/operation_controls.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _headC =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const _event =
    'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd';

OperationSnapshot _snapshot(String state,
        {String head = _headA, bool canCancel = false, String? resultSha256}) =>
    OperationSnapshot.fromJson({
      'schema': 'flywheel.gateway-operation-snapshot/v1',
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': state == 'cancelled' ? _event : null,
      'result_sha256': state == 'cancelled' ? resultSha256 ?? _headB : null,
    });

String _resultDigest() => sha256
    .convert(utf8.encode('{"action":"agent.run","operation_ref":"$_operation",'
        '"result":{"stopped":true},"schema":"flywheel.gateway-operation-result/v1",'
        '"state":"cancelled"}'))
    .toString();

void main() {
  _stopGrantTest();
  _stopStateTests();
  _stopWidgetTest();
  _operationClientTests();
  _operationClientAdversaryTests();
}

void _stopGrantTest() {
  test('Stop is an exact stable one-use operation bound to latest snapshot',
      () {
    var requestCalls = 0;
    final controller = OperationController(
        requestId: () => 'stop-${++requestCalls}', stopTimeoutMs: 4500);
    controller.acceptSnapshot(_snapshot('running', canCancel: true));
    final first = controller.stopOperation();
    final replay = controller.stopOperation();

    expect(first, isNotNull);
    expect(replay, first);
    expect(first!.action, 'operation.cancel');
    expect(first.clientRequestId, 'stop-1');
    expect(first.destination.kind, 'operation');
    expect(first.destination.ref, _operation);
    expect(first.tool, 'operation.cancel');
    expect(first.scopes, ['exec']);
    expect(first.operation, {
      'operation_ref': _operation,
      'timeout_ms': 4500,
      'data_refs': <String>[],
      'credential_refs': <String>[],
    });
    expect(
        first.finalBody(const GatewayJourneyBinding(_journey, _headA),
            'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        {
          'schema': 'flywheel.gateway-operation/v1',
          'journey_ref': _journey,
          'expected_event_head': _headA,
          'client_request_id': 'stop-1',
          'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'operation_ref': _operation,
          'timeout_ms': 4500,
          'data_refs': <String>[],
          'credential_refs': <String>[],
        });
    controller.dispose();
  });
}

void _stopStateTests() {
  test('snapshot change invalidates approval and stopping stays nonterminal',
      () {
    var terminals = 0;
    final controller = OperationController(
        requestId: () => 'stop-1', onTerminal: () => terminals++);
    controller.acceptSnapshot(_snapshot('running', canCancel: true));
    final pending = controller.stopOperation();
    expect(pending, isNotNull);

    controller.acceptSnapshot(_snapshot('cancel_requested', head: _headB));
    expect(controller.stopOperation(), isNull);
    expect(controller.isPendingOperation(pending!), isFalse);
    expect(controller.execution?.state, OperationState.cancelRequested);
    expect(terminals, 0);

    controller.closeObservation();
    expect(controller.execution?.state, OperationState.cancelRequested);
    expect(terminals, 0);
    controller.dispose();
  });

  test('valid terminal unlocks once and disposal is observational only', () {
    var terminals = 0;
    final controller = OperationController(
        requestId: () => 'stop-1', onTerminal: () => terminals++);
    controller.acceptSnapshot(_snapshot('running', canCancel: true));
    controller.dispose();
    expect(terminals, 0);

    final active = OperationController(
        requestId: () => 'stop-2', onTerminal: () => terminals++);
    active.acceptSnapshot(_snapshot('running', canCancel: true));
    active.acceptSnapshot(_snapshot('cancel_requested', head: _headB));
    final terminal =
        _snapshot('cancelled', head: _headC, resultSha256: _resultDigest());
    final result = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'cancelled',
      'result': {'stopped': true},
    });
    expect(active.acceptTerminal(terminal, result), isTrue);
    expect(active.acceptTerminal(terminal, result), isTrue);
    expect((active.execution?.state, terminals), (OperationState.cancelled, 1));
    active.dispose();
  });
}

void _stopWidgetTest() {
  testWidgets('Stop taps once and cancel requested renders Stopping…',
      (tester) async {
    var stops = 0;
    Widget controls(OperationSnapshot snapshot) => MaterialApp(
        home: Scaffold(
            body: OperationControls(
                alive: true,
                authorizing: false,
                snapshot: snapshot,
                onRun: () {},
                onStop: () => stops++)));
    await tester.pumpWidget(controls(_snapshot('running', canCancel: true)));
    expect(find.byKey(const ValueKey('operation-stop')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('operation-stop')));
    expect(stops, 1);

    await tester
        .pumpWidget(controls(_snapshot('cancel_requested', head: _headB)));
    expect(find.text('Stopping…'), findsOneWidget);
    expect(find.byKey(const ValueKey('operation-stop')), findsNothing);
  });
}

void _operationClientTests() {
  test('operation client parses exact start watch cancel snapshot and result',
      () async {
    final running = _snapshot('running', canCancel: true);
    final stopping = _snapshot('cancel_requested', head: _headB);
    final result = <String, Object?>{
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'cancelled',
      'result': {'stopped': true},
    };
    final terminal =
        _snapshot('cancelled', head: _headC, resultSha256: _resultDigest());
    var snapshotCalls = 0;
    String frame(int id, String type, Object data) =>
        'id: $id\r\nevent: $type\r\ndata: ${jsonEncode(data)}\r\n\r\n';
    final stream = '${frame(8, 'snapshot', running.toJson())}'
        '${frame(9, 'snapshot', stopping.toJson())}'
        '${frame(10, 'terminal', {
          'snapshot': terminal.toJson(),
          'result': result
        })}'
        'id: 11\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((request) async {
          if (request.url.path.endsWith('/events') ||
              request.url.path == '/api/agent') {
            return http.Response(stream, 200);
          }
          if (request.url.path.endsWith('/result')) {
            return http.Response(jsonEncode(result), 200);
          }
          if (request.url.path == '/api/operations/cancel') {
            expect(jsonDecode(request.body)['operation_ref'], _operation);
            return http.Response(jsonEncode(stopping.toJson()), 200);
          }
          return http.Response(
              jsonEncode((++snapshotCalls == 1 ? running : terminal).toJson()),
              200);
        }));
    final operations = GatewayOperations(client);

    expect((await operations.start({'request': 'exact'}).toList()).length, 4);
    expect(
        (await operations.watch(_operation, afterSequence: 7).toList())
            .last
            .isDone,
        isTrue);
    expect(
        (await operations.snapshot(_operation)).state, OperationState.running);
    expect((await operations.result(_operation)).result, {'stopped': true});
    expect((await operations.cancel({'operation_ref': _operation})).state,
        OperationState.cancelRequested);
    client.close();
  });
}

void _operationClientAdversaryTests() {
  test('watch rejects ids at or before requested sequence', () async {
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((_) async => http.Response(
            'id: 7\nevent: terminal\ndata: {"snapshot":{},"result":{}}\n\n',
            200)));
    await expectLater(
        GatewayOperations(client).watch(_operation, afterSequence: 7),
        emitsError(isA<GatewaySseException>()));
    client.close();
  });

  test('operation error stream is bounded before public decoding', () async {
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((_) async => http.Response('x' * 1048577, 502)));
    await expectLater(GatewayOperations(client).start({'request': 'exact'}),
        emitsError(isA<GatewaySseException>()));
    client.close();
  });

  test('review W11 terminal event rejects noncanonical result digest',
      () async {
    final result = <String, Object?>{
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'cancelled',
      'result': {'stopped': true},
    };
    final terminal = _snapshot('cancelled', head: _headC);
    final wire = 'id: 1\nevent: terminal\ndata: ${jsonEncode({
          'snapshot': terminal.toJson(),
          'result': result
        })}\n\n';
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((_) async => http.Response(wire, 200)));
    await expectLater(GatewayOperations(client).start(const {}),
        emitsError(isA<GatewaySseException>()));
    client.close();
  });

  test('review W11 standalone result requires terminal snapshot', () async {
    final result = <String, Object?>{
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'cancelled',
      'result': {'stopped': true},
    };
    final client = GatewayClient(
        baseUrl: 'http://gateway.test',
        httpClient: MockClient((request) async => http.Response(
            jsonEncode(request.url.path.endsWith('/result')
                ? result
                : _snapshot('running', canCancel: true).toJson()),
            200)));
    await expectLater(GatewayOperations(client).result(_operation),
        throwsA(isA<GatewaySseException>()));
    client.close();
  });
}
