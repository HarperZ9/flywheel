import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_sse_decoder.dart';
import 'package:flywheel_desktop/models/operation_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _headC =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';

Map<String, Object?> _snapshot(
  String state, {
  String head = _headA,
  bool canCancel = false,
  String? terminal,
  String? result,
}) =>
    {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': terminal,
      'result_sha256': result,
    };

void main() {
  _operationListTests();
  _numericDomainTests();
}

void _operationListTests() {
  test('operation discovery parses snapshots plus request hash map only', () {
    final page = OperationListPage.fromJson({
      'schema': operationListSchema,
      'journey_ref': _journey,
      'event_head_sha256': _headA,
      'operations': [_snapshot('running', canCancel: false)],
      'request_sha256_by_operation': {_operation: _headB},
      'next_cursor': null,
    });
    expect(page.operations.single.operationRef, _operation);
    expect(page.requestSha256ByOperation[_operation], _headB);

    expect(
      () => OperationListPage.fromJson({
        'schema': operationListSchema,
        'journey_ref': _journey,
        'event_head_sha256': _headA,
        'operations': [_snapshot('running', canCancel: true)],
        'request_sha256_by_operation': {_operation: _headB},
        'next_cursor': null,
      }),
      throwsArgumentError,
    );
    expect(
      () => OperationListPage.fromJson({
        'schema': operationListSchema,
        'journey_ref': _journey,
        'event_head_sha256': _headA,
        'operations': [_snapshot('running', canCancel: false)],
        'request_sha256_by_operation': {
          'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb': _headB,
        },
        'next_cursor': null,
      }),
      throwsArgumentError,
    );
    expect(
      () => OperationListPage.fromJson({
        'schema': operationListSchema,
        'journey_ref': _journey,
        'event_head_sha256': _headA,
        'operations': [_snapshot('running', canCancel: false)],
        'request_sha256_by_operation': const {},
        'next_cursor': null,
      }),
      throwsArgumentError,
    );
    expect(
      () => OperationListPage.fromJson({
        'schema': operationListSchema,
        'journey_ref': _journey,
        'event_head_sha256': _headA,
        'operations': [
          _snapshot('running', canCancel: false),
          _snapshot('queued', canCancel: false),
        ],
        'request_sha256_by_operation': {_operation: _headB},
        'next_cursor': null,
      }),
      throwsArgumentError,
    );
  });

  test('operation discovery client encodes journey limit and cursor', () async {
    late Uri seen;
    final client = GatewayClient(
      baseUrl: 'http://gateway.test',
      httpClient: MockClient((request) async {
        seen = request.url;
        return http.Response(
          jsonEncode({
            'schema': operationListSchema,
            'journey_ref': _journey,
            'event_head_sha256': _headA,
            'operations': [_snapshot('queued', canCancel: false)],
            'request_sha256_by_operation': {_operation: _headB},
            'next_cursor': 'cursor-2',
          }),
          200,
        );
      }),
    );
    final page = await GatewayOperations(
      client,
    ).listByJourney(_journey, limit: 12, cursor: 'cursor-1');
    expect(seen.path, '/api/operations');
    expect(seen.queryParameters['journey_ref'], _journey);
    expect(seen.queryParameters['limit'], '12');
    expect(seen.queryParameters['cursor'], 'cursor-1');
    expect(page.nextCursor, 'cursor-2');
    client.close();
  });
}

void _numericDomainTests() {
  const valid = '{"action":"agent.run","operation_ref":"$_operation",'
      '"result":{"max64":9223372036854775807,'
      '"min64":-9223372036854775808,"minus53":-9007199254740992,'
      '"plus53":9007199254740992},'
      '"schema":"flywheel.gateway-operation-result/v1",'
      '"state":"completed"}';
  test('operation result shares exact signed64 integer domain with server', () {
    final result = OperationResult.fromJson(
      Map<String, Object?>.from(jsonDecode(valid) as Map),
    );
    expect(result.result['minus53'], -9007199254740992);
    expect(result.result['plus53'], 9007199254740992);
    expect(result.result['min64'], -9223372036854775808);
    expect(result.result['max64'], 9223372036854775807);
    expect(
      result.canonicalSha256,
      'ae2e1e88cc232bbe608404be0efb6ed20f43d72db9b018a1fd3d80cea64544a8',
    );
  });

  test('standalone result rejects an integer lexeme beyond signed64', () async {
    const overflow = '{"schema":"flywheel.gateway-operation-result/v1",'
        '"operation_ref":"$_operation","action":"agent.run",'
        '"state":"completed","result":{"value":9223372036854775808}}';
    final decoded = OperationResult.fromJson(
      Map<String, Object?>.from(jsonDecode(overflow) as Map),
    );
    final terminal = _snapshot(
      'completed',
      terminal: _headC,
      result: decoded.canonicalSha256,
    );
    final client = GatewayClient(
      baseUrl: 'http://gateway.test',
      httpClient: MockClient(
        (request) async => request.url.path.endsWith('/result')
            ? http.Response(overflow, 200)
            : http.Response(jsonEncode(terminal), 200),
      ),
    );
    await expectLater(
      GatewayOperations(client).result(_operation),
      throwsA(isA<GatewaySseException>()),
    );
    client.close();
  });
}
