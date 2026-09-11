import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_$_a';
const _operation = 'op_$_a';
const _head = '$_a$_a';

Future<BuildContext> _mount(
  WidgetTester tester,
  GatewayOperationAuthorizer authorize,
) async {
  late BuildContext context;
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: GatewayOperationScope(
      authorize: authorize,
      child: Builder(builder: (ctx) {
        context = ctx;
        return const SizedBox.shrink();
      }),
    ),
  ));
  return context;
}

Map<String, Object?> _snapshot(
  String state, {
  String operation = _operation,
  String journey = _journey,
}) =>
    {
      'schema': operationSnapshotSchema,
      'operation_ref': operation,
      'journey_ref': journey,
      'event_head_sha256': _head,
      'state': state,
      'can_cancel': false,
      'terminal_event_ref': null,
      'result_sha256': null,
    };

OperationResult _result(String finalText, {String operation = _operation}) =>
    OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {'final': finalText},
    });

Map<String, Object?> _terminalSnapshot(
  OperationResult result, {
  String operation = _operation,
  String head = _head,
  String? resultSha256,
}) =>
    {
      'schema': operationSnapshotSchema,
      'operation_ref': operation,
      'journey_ref': _journey,
      'event_head_sha256': head,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': 'b' * 64,
      'result_sha256': resultSha256 ?? result.canonicalSha256,
    };

JourneySessionStore _store(
  String name,
  String requestHash, {
  String? operationRef,
  String? operationExecutionMode,
}) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return JourneySessionStore(
      file: File('${directory.path}${Platform.pathSeparator}session.json'))
    ..save(JourneySession(
      journeyRef: _journey,
      lens: JourneyLens.verify,
      operationRef: operationRef,
      operationEventHeadSha256: operationRef == null ? null : _head,
      operationRequestSha256: requestHash,
      operationExecutionMode: operationExecutionMode,
    ));
}

void main() {
  testWidgets('unavailable recovery blocks duplicate start until dismissed',
      (tester) async {
    final requestHash = rowanRequestIdSha256('rowan-agent-missing');
    var authorizes = 0, posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations') {
          return http.Response('temporarily unavailable', 503);
        }
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 404);
      }),
    );
    final store = _store(
      'blocked-',
      requestHash,
      operationExecutionMode: 'native_cli_session',
    );
    final rowan = RowanOperationController(client, sessionStore: store)
      ..setEndpoint('local');
    addTearDown(rowan.dispose);

    expect(await rowan.recoverFromSession(), isFalse);
    expect(rowan.error, 'OPERATION_RECOVERY_PENDING');

    final context = await _mount(tester, (_, __, ___, ____) async {
      authorizes++;
      return const GatewayAuthorizationOutcome.denied();
    });
    final blocked = await rowan.start(context, 'do not duplicate');
    expect(blocked.failure?.code, 'OPERATION_RECOVERY_PENDING');
    expect((authorizes, posts), (0, 0));

    rowan.dismissRecoveryBlock();
    expect(store.load()?.operationRequestSha256, isNull);
    expect(store.load()?.operationExecutionMode, 'native_cli_session');
    rowan
      ..setEndpoint('claude-cli')
      ..setModel('fixture-model-exact')
      ..setWorkspaceRoot(r'C:\fixture\workspace');
    expect(
        (await rowan.start(context, 'explicit new operation')).denied, isTrue);
    expect((authorizes, posts), (1, 0));
    client.close();
  });

  testWidgets(
    'stale direct ref with request hash blocks duplicate start',
    (tester) async {
      final requestHash = rowanRequestIdSha256('rowan-agent-stale-direct');
      var authorizes = 0, posts = 0;
      const stale = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
      const staleJourney = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
      final client = GatewayClient(
        baseUrl: 'https://rowan.invalid',
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/operations/$stale' &&
              !request.url.hasQuery) {
            return http.Response(
              jsonEncode(_snapshot(
                'running',
                operation: stale,
                journey: staleJourney,
              )),
              200,
            );
          }
          if (request.url.path == '/api/operations') {
            return http.Response('temporarily unavailable', 503);
          }
          if (request.url.path == '/api/agent') posts++;
          return http.Response('{}', 404);
        }),
      );
      final rowan = RowanOperationController(
        client,
        sessionStore: _store(
          'stale-direct-',
          requestHash,
          operationRef: stale,
        ),
      )..setEndpoint('local');
      addTearDown(rowan.dispose);

      expect(await rowan.recoverFromSession(), isFalse);
      expect(rowan.error, 'OPERATION_RECOVERY_PENDING');

      final context = await _mount(tester, (_, __, ___, ____) async {
        authorizes++;
        return const GatewayAuthorizationOutcome.denied();
      });
      final blocked = await rowan.start(context, 'do not duplicate stale ref');
      expect(blocked.failure?.code, 'OPERATION_RECOVERY_PENDING');
      expect((authorizes, posts), (0, 0));
      client.close();
    },
  );

  testWidgets('hash match with failed reconnect keeps duplicate blocker',
      (tester) async {
    final requestHash = rowanRequestIdSha256('rowan-agent-found-but-stale');
    final mismatched = _result('fresh body does not match advertised hash');
    var authorizes = 0, posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations') {
          return http.Response(
              jsonEncode({
                'schema': operationListSchema,
                'journey_ref': _journey,
                'event_head_sha256': _head,
                'operations': [
                  _terminalSnapshot(mismatched, resultSha256: 'c' * 64)
                ],
                'request_sha256_by_operation': {_operation: requestHash},
                'next_cursor': null,
              }),
              200);
        }
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          return http.Response(
              jsonEncode(_terminalSnapshot(mismatched, resultSha256: 'c' * 64)),
              200);
        }
        if (request.url.path == '/api/operations/$_operation/result') {
          return http.Response(jsonEncode(mismatched.toJson()), 200);
        }
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(
      client,
      sessionStore: _store('found-blocked-', requestHash),
    )..setEndpoint('local');
    addTearDown(rowan.dispose);

    expect(await rowan.recoverFromSession(), isFalse);
    expect(rowan.error, 'OPERATION_RECOVERY_PENDING');

    final context = await _mount(tester, (_, __, ___, ____) async {
      authorizes++;
      return const GatewayAuthorizationOutcome.denied();
    });
    final blocked = await rowan.start(context, 'do not duplicate after match');
    expect(blocked.failure?.code, 'OPERATION_RECOVERY_PENDING');
    expect((authorizes, posts), (0, 0));
    client.close();
  });

  test('reconnect fails when fresh terminal state is rejected', () async {
    final oldResult = _result('old accepted result');
    final freshResult = _result('fresh but incompatible result');
    var resultReads = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          return http.Response(
              jsonEncode(_terminalSnapshot(
                freshResult,
                head: 'd' * 64,
              )),
              200);
        }
        if (request.url.path == '/api/operations/$_operation/result') {
          resultReads++;
          return http.Response(jsonEncode(freshResult.toJson()), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client);
    addTearDown(rowan.dispose);
    final oldSnapshot =
        OperationSnapshot.fromJson(_terminalSnapshot(oldResult));
    expect(rowan.operationState.acceptTerminal(oldSnapshot, oldResult), isTrue);

    expect(await rowan.reconnect(oldSnapshot), isFalse);
    expect(rowan.snapshot, oldSnapshot);
    expect(resultReads, 1);
    client.close();
  });
}
