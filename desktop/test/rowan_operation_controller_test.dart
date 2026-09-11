import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_$_a';
const _operation = 'op_$_a';
const _headA = '$_a$_a';
const _grant = 'gnt_$_a';

Map<String, Object?> _snapshot(
  String state, {
  String operation = _operation,
  String journey = _journey,
  String head = _headA,
  bool canCancel = false,
}) =>
    {
      'schema': operationSnapshotSchema,
      'operation_ref': operation,
      'journey_ref': journey,
      'event_head_sha256': head,
      'state': state,
      'can_cancel': canCancel,
      'terminal_event_ref': null,
      'result_sha256': null,
    };

Directory _temporary(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

Future<BuildContext> _mount(
  WidgetTester tester,
  GatewayOperationAuthorizer authorize,
) async {
  late BuildContext context;
  await tester.pumpWidget(
    MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: authorize,
        child: Builder(
          builder: (ctx) {
            context = ctx;
            return const SizedBox.shrink();
          },
        ),
      ),
    ),
  );
  return context;
}

void main() {
  testWidgets('denied Rowan approval sends no task', (tester) async {
    var posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 500);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('local');
    addTearDown(rowan.dispose);
    final context = await _mount(
      tester,
      (_, __, ___, ____) async => const GatewayAuthorizationOutcome.denied(),
    );

    final outcome = await rowan.start(context, 'inspect');
    expect(outcome.denied, isTrue);
    expect(posts, 0);
    expect(rowan.snapshot, isNull);
    client.close();
  });

  testWidgets('denied Rowan approval leaves no pending request locator', (
    tester,
  ) async {
    var posts = 0;
    final directory = Directory.systemTemp.createTempSync('rowan-denied-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final store = JourneySessionStore(
      file: File('${directory.path}${Platform.pathSeparator}session.json'),
    )..save(JourneySession(journeyRef: _journey, lens: JourneyLens.verify));
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 500);
      }),
    );
    final rowan = RowanOperationController(client, sessionStore: store)
      ..setEndpoint('local');
    addTearDown(rowan.dispose);
    final context = await _mount(
      tester,
      (_, __, ___, ____) async => const GatewayAuthorizationOutcome.denied(),
    );

    final outcome = await rowan.start(context, 'inspect');
    expect(outcome.denied, isTrue);
    expect(posts, 0);
    expect(rowan.snapshot, isNull);
    expect(store.load()?.operationRequestSha256, isNull);
    client.close();
  });

  testWidgets('running operation suppresses duplicate start POST', (
    tester,
  ) async {
    var posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') {
          posts++;
          return http.Response(
            'id: 1\nevent: snapshot\ndata: ${jsonEncode(_snapshot('running', canCancel: true))}\n\n',
            200,
          );
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('local');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (
      context,
      operation,
      current,
      dispatch,
    ) {
      return dispatch(
        operation.finalBody(
          const GatewayJourneyBinding(_journey, _headA),
          _grant,
        ),
      );
    });

    expect((await rowan.start(context, 'inspect')).value, isTrue);
    expect(
        rowan.operationState.observerState, OperationObserverState.connecting);
    final connecting = await rowan.start(context, 'inspect while connecting');
    expect(connecting.failure?.code, 'OPERATION_ACTIVE');
    await tester.pump();
    expect(rowan.snapshot?.state, OperationState.running);
    final running = await rowan.start(context, 'inspect again');
    expect(running.failure?.code, 'OPERATION_ACTIVE');
    expect(posts, 1);
    client.close();
  });

  testWidgets('model change invalidates pending Rowan approval', (
    tester,
  ) async {
    final release = Completer<void>();
    late GatewayOperationSupplier current;
    final client = GatewayClient(baseUrl: 'https://rowan.invalid');
    final rowan = RowanOperationController(client)
      ..setEndpoint('local')
      ..setModel('model-a');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (
      _,
      operation,
      supplier,
      dispatch,
    ) async {
      current = supplier;
      await release.future;
      return current() == null
          ? const GatewayAuthorizationOutcome.denied()
          : GatewayAuthorizationOutcome.value(
              await dispatch(
                operation.finalBody(
                  const GatewayJourneyBinding(_journey, _headA),
                  _grant,
                ),
              ),
            );
    });

    final pending = rowan.start(context, 'inspect');
    await tester.pump();
    rowan.setModel('model-b');
    release.complete();
    final outcome = await pending;
    expect(outcome.denied, isTrue);
    expect(rowan.snapshot, isNull);
    client.close();
  });

  test(
    'lost first response recovers exact operation by request hash',
    () async {
      final directory = _temporary('rowan-recover-');
      final requestHash = rowanRequestIdSha256('rowan-agent-1');
      final store = JourneySessionStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}session.json',
        ),
      )..save(
          JourneySession(
            journeyRef: _journey,
            lens: JourneyLens.verify,
            operationRequestSha256: requestHash,
          ),
        );
      var posts = 0, lists = 0, snapshots = 0, watches = 0;
      final client = GatewayClient(
        baseUrl: 'https://rowan.invalid',
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/agent') posts++;
          if (request.url.path == '/api/operations' &&
              request.url.queryParameters['journey_ref'] == _journey) {
            lists++;
            return http.Response(
              jsonEncode({
                'schema': operationListSchema,
                'journey_ref': _journey,
                'event_head_sha256': _headA,
                'operations': [_snapshot('running')],
                'request_sha256_by_operation': {_operation: requestHash},
                'next_cursor': null,
              }),
              200,
            );
          }
          if (request.url.path == '/api/operations/$_operation' &&
              !request.url.hasQuery) {
            snapshots++;
            return http.Response(jsonEncode(_snapshot('running')), 200);
          }
          if (request.url.path == '/api/operations/$_operation/events') {
            watches++;
            return http.Response(
                'id: 2\nevent: terminal\ndata: [DONE]\n\n', 200);
          }
          return http.Response('{}', 404);
        }),
      );
      final rowan = RowanOperationController(client, sessionStore: store);
      addTearDown(rowan.dispose);

      expect(await rowan.recoverFromSession(), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(rowan.snapshot?.operationRef, _operation);
      expect((posts, lists, snapshots, watches), (0, 1, 1, 1));
      client.close();
    },
  );

  test('agent.run accepts remote gateway roots and strict model IDs', () {
    expect(
      () => GatewayOperation.exact(
        action: 'agent.run',
        clientRequestId: 'request-1',
        operation: const {
          'goal': 'inspect',
          'endpoint': 'local',
          'model': 'qwen2.5-coder:14b',
          'root': '/srv/remote/workspace',
          'max_steps': 3,
          'max_tokens': 1024,
          'timeout_s': 300,
          'allow_write': false,
          'allow_exec': false,
          'stream': true,
        },
      ),
      returnsNormally,
    );
    final rowan = RowanOperationController(GatewayClient())
      ..setEndpoint('local');
    addTearDown(rowan.dispose);
    rowan.setModel('bad model');
    expect(rowan.error, 'INVALID_MODEL');
  });
}
