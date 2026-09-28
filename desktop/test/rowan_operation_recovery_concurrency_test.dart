import 'dart:async';
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

JourneySessionStore _store(
  String name, {
  String? operationRef = _operation,
  String? requestSha256,
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
      operationRequestSha256: requestSha256,
    ));
}

Map<String, Object?> _snapshot(String state, {String journey = _journey}) => {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': journey,
      'event_head_sha256': _head,
      'state': state,
      'can_cancel': false,
      'terminal_event_ref': null,
      'result_sha256': null,
    };

OperationResult _result(String finalText) => OperationResult.fromJson({
      'schema': operationResultSchema,
      'operation_ref': _operation,
      'action': 'agent.run',
      'state': 'completed',
      'result': {'final': finalText},
    });

Map<String, Object?> _terminalSnapshot(OperationResult result) => {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': 'b' * 64,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': 'c' * 64,
      'result_sha256': result.canonicalSha256,
    };

String _terminalSse(String finalText) {
  final result = _result(finalText);
  return 'id: 2\nevent: terminal\ndata: ${jsonEncode({
        'snapshot': _terminalSnapshot(result),
        'result': result.toJson(),
      })}\n\n'
      'id: 3\nevent: terminal\ndata: [DONE]\n\n';
}

void main() {
  testWidgets('in-flight recovery blocks a new local start', (tester) async {
    final snapshotRequested = Completer<void>();
    final releaseSnapshot = Completer<void>();
    var snapshots = 0, watches = 0, authorizes = 0, posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          snapshots++;
          if (!snapshotRequested.isCompleted) snapshotRequested.complete();
          await releaseSnapshot.future;
          return http.Response(jsonEncode(_snapshot('running')), 200);
        }
        if (request.url.path == '/api/operations/$_operation/events') {
          watches++;
          return http.Response(_terminalSse('recovered run finished'), 200);
        }
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);
    final rowan = RowanOperationController(
      client,
      sessionStore: _store(
        'rowan-recovery-race-',
        requestSha256: rowanRequestIdSha256('rowan-agent-race'),
      ),
    )..setEndpoint('local');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (_, __, ___, ____) async {
      authorizes++;
      return const GatewayAuthorizationOutcome.denied();
    });

    final recovery = rowan.recoverFromSession();
    await snapshotRequested.future;
    expect(rowan.active, isTrue);

    final blocked = await rowan.start(context, 'new local operation');
    expect(blocked.failure?.code, 'OPERATION_ACTIVE');
    expect(rowan.snapshot, isNull);
    expect((authorizes, posts), (0, 0));

    releaseSnapshot.complete();
    expect(await recovery, isTrue);
    await tester.pump();
    expect(rowan.snapshot?.operationRef, _operation);
    expect((snapshots, watches), (2, 1));
  });

  test('concurrent recovery calls share the same gateway snapshot', () async {
    final snapshotRequested = Completer<void>();
    final releaseSnapshot = Completer<void>();
    var snapshots = 0, watches = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          snapshots++;
          if (!snapshotRequested.isCompleted) snapshotRequested.complete();
          await releaseSnapshot.future;
          return http.Response(jsonEncode(_snapshot('running')), 200);
        }
        if (request.url.path == '/api/operations/$_operation/events') {
          watches++;
          return http.Response(_terminalSse('shared recovery finished'), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);
    final rowan = RowanOperationController(
      client,
      sessionStore: _store('rowan-recovery-shared-'),
    );
    addTearDown(rowan.dispose);

    final first = rowan.recoverFromSession();
    final second = rowan.recoverFromSession();
    await snapshotRequested.future;
    releaseSnapshot.complete();

    expect(await first, isTrue);
    expect(await second, isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(rowan.snapshot?.operationRef, _operation);
    expect((snapshots, watches), (2, 1));
  });

  testWidgets('failed direct recovery does not orphan the busy gate',
      (tester) async {
    var authorizes = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          return http.Response('temporarily unavailable', 503);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);
    final rowan = RowanOperationController(
      client,
      sessionStore: _store('rowan-recovery-error-', requestSha256: null),
    )..setEndpoint('local');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (_, __, ___, ____) async {
      authorizes++;
      return const GatewayAuthorizationOutcome.denied();
    });

    expect(await rowan.recoverFromSession(), isFalse);
    expect(rowan.active, isFalse);
    expect((await rowan.start(context, 'start after failed recovery')).denied,
        isTrue);
    expect(authorizes, 1);
  });
}
