import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_sse_decoder.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _otherOperation = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  test('provider session paths are the only new operation SSE paths', () async {
    // Break this catches: deleting the provider-session path admission makes
    // the desktop grant flow unable to dispatch the operation the backend owns.
    final seen = <String>[];
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient.streaming((request, _) async {
        seen.add(request.url.path);
        final result = OperationResult.fromJson({
          'schema': operationResultSchema,
          'operation_ref': _operation,
          'action': providerSessionTurnAction,
          'state': 'completed',
          'result': {
            'provider_session': {
              'provider': 'codex',
              'native_thread_id': 'thread-1',
              'config_digest': _sha,
            },
            'history_status': 'complete',
            'side_effect_status': 'none',
          },
        });
        final terminal = {
          'snapshot': {
            'schema': operationSnapshotSchema,
            'operation_ref': _operation,
            'journey_ref': 'jrn_$_a',
            'event_head_sha256': _sha,
            'state': 'completed',
            'can_cancel': false,
            'terminal_event_ref': _sha,
            'result_sha256': result.canonicalSha256,
          },
          'result': result.toJson(),
        };
        return http.StreamedResponse(
          Stream.value(utf8.encode(
            'id: 1\r\nevent: progress\r\n'
            'data: {"provider_session":{"phase":"native_binding",'
            '"provider":"codex","operation_ref":"$_operation",'
            '"native_thread_id":"thread-1"}}\r\n\r\n'
            'id: 2\r\nevent: terminal\r\ndata: ${jsonEncode(terminal)}\r\n\r\n'
            'id: 3\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n',
          )),
          200,
        );
      }),
    );
    addTearDown(client.close);

    final events = await GatewayOperations(client)
        .start({'schema': 'test'}, path: providerSessionTurnPath).toList();

    expect(seen, [providerSessionTurnPath]);
    final progress = events.where(
      (event) => event.type == GatewayOperationEventType.progress,
    );
    expect(progress.single.progress?['provider_session']['phase'],
        'native_binding');
    expect(events.last.type, GatewayOperationEventType.done);
    await expectLater(
      GatewayOperations(client).start({'schema': 'test'},
          path: '/api/provider-sessions/delete').drain<void>(),
      throwsA(isA<GatewaySseException>()),
    );
  });

  test('operation results accept provider session terminal actions', () {
    // Break this catches: a provider turn can finish in the backend but the
    // desktop terminal parser rejects the action before it reaches the UI.
    final result = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': providerSessionTurnAction,
      'state': 'failed',
      'result': {
        'reason': 'AGENT_NATIVE_INCOMPLETE',
        'provider_session': {
          'provider': 'codex',
          'native_thread_id': 'thread-1',
          'config_digest': _sha,
        },
        'history_status': 'indeterminate',
        'side_effect_status': 'unknown_after_send',
      },
    });

    expect(result.action, providerSessionTurnAction);
    expect(result.state, OperationState.failed);
  });

  test('watch rejects terminal events for a different operation ref', () async {
    // Break this catches: a watch stream follows the requested URL but accepts
    // a terminal snapshot/result for another operation as if it were watched.
    final result = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _otherOperation,
      'action': providerSessionTurnAction,
      'state': 'completed',
      'result': {
        'provider_session': {
          'provider': 'codex',
          'native_thread_id': 'thread-1',
          'config_digest': _sha,
        },
        'history_status': 'complete',
        'side_effect_status': 'input_sent',
      },
    });
    final terminal = {
      'snapshot': {
        'schema': operationSnapshotSchema,
        'operation_ref': _otherOperation,
        'journey_ref': 'jrn_$_a',
        'event_head_sha256': _sha,
        'state': 'completed',
        'can_cancel': false,
        'terminal_event_ref': _sha,
        'result_sha256': result.canonicalSha256,
      },
      'result': result.toJson(),
    };
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient.streaming((request, _) async {
        expect(request.url.path, '/api/operations/$_operation/events');
        return http.StreamedResponse(
          Stream.value(utf8.encode(
            'id: 1\r\nevent: terminal\r\ndata: ${jsonEncode(terminal)}\r\n\r\n'
            'id: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n',
          )),
          200,
        );
      }),
    );
    addTearDown(client.close);

    await expectLater(
      GatewayOperations(client).watch(_operation).drain<void>(),
      throwsA(isA<GatewaySseException>()),
    );
  });

  test('watch rejects provider progress for a different operation ref',
      () async {
    // Break this catches: a raw operation watch consumer sees progress/native
    // ids from another provider session before the controller can filter it.
    final result = OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': providerSessionTurnAction,
      'state': 'completed',
      'result': {
        'provider_session': {
          'provider': 'codex',
          'native_thread_id': 'thread-1',
          'config_digest': _sha,
        },
        'history_status': 'complete',
        'side_effect_status': 'input_sent',
      },
    });
    final terminal = {
      'snapshot': {
        'schema': operationSnapshotSchema,
        'operation_ref': _operation,
        'journey_ref': 'jrn_$_a',
        'event_head_sha256': _sha,
        'state': 'completed',
        'can_cancel': false,
        'terminal_event_ref': _sha,
        'result_sha256': result.canonicalSha256,
      },
      'result': result.toJson(),
    };
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient.streaming((request, _) async {
        expect(request.url.path, '/api/operations/$_operation/events');
        return http.StreamedResponse(
          Stream.value(utf8.encode(
            'id: 1\r\nevent: progress\r\n'
            'data: {"provider_session":{"phase":"native_binding",'
            '"provider":"codex","operation_ref":"$_otherOperation",'
            '"native_thread_id":"thread-b"}}\r\n\r\n'
            'id: 2\r\nevent: terminal\r\ndata: ${jsonEncode(terminal)}\r\n\r\n'
            'id: 3\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n',
          )),
          200,
        );
      }),
    );
    addTearDown(client.close);

    await expectLater(
      GatewayOperations(client).watch(_operation).drain<void>(),
      throwsA(isA<GatewaySseException>()),
    );
  });
}
