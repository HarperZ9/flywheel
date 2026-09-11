import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/agent_tool_protocol.dart';
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
const _grant = 'gnt_$_a';

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

JourneySessionStore _store(
  String name,
  String requestHash,
) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return JourneySessionStore(
      file: File('${directory.path}${Platform.pathSeparator}session.json'))
    ..save(JourneySession(
      journeyRef: _journey,
      lens: JourneyLens.verify,
      operationRequestSha256: requestHash,
    ));
}

void main() {
  testWidgets('native tool protocol is frozen only after explicit selection',
      (tester) async {
    final prepared = <Map<String, Object?>>[];
    final dispatched = <Map<String, dynamic>>[];
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') {
          dispatched.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(
              'id: 1\nevent: snapshot\ndata: ${jsonEncode(_snapshot('running'))}\n\n',
              200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)
      ..setEndpoint('local')
      ..setWorkspaceRoot(r'\\DESKTOP-GATEWAY\workspace');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (_, operation, __, dispatch) async {
      prepared.add(Map<String, Object?>.from(operation.operation));
      if (!operation.operation.containsKey('tool_protocol')) {
        return const GatewayAuthorizationOutcome.denied();
      }
      return dispatch(operation.finalBody(
          const GatewayJourneyBinding(_journey, _head), _grant));
    });

    expect((await rowan.start(context, 'default tools')).denied, isTrue);
    expect(prepared.single.containsKey('tool_protocol'), isFalse);
    expect(dispatched, isEmpty);

    rowan.setToolProtocol(AgentToolProtocol.native);
    expect((await rowan.start(context, 'native tools')).value, isTrue);
    await tester.pump();
    expect(prepared.last['tool_protocol'], 'native');
    expect(dispatched.single['tool_protocol'], 'native');
    expect(dispatched.single['root'], r'\\DESKTOP-GATEWAY\workspace');
    client.close();
  });

  test('lost first response recovers request hash from page two', () async {
    final requestHash = rowanRequestIdSha256('rowan-agent-1');
    var lists = 0, snapshots = 0, watches = 0, posts = 0;
    const other = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') posts++;
        if (request.url.path == '/api/operations') {
          lists++;
          final second = request.url.queryParameters['cursor'] == 'page-2';
          return http.Response(
              jsonEncode({
                'schema': operationListSchema,
                'journey_ref': _journey,
                'event_head_sha256': _head,
                'operations': [
                  _snapshot('running', operation: second ? _operation : other)
                ],
                'request_sha256_by_operation': {
                  second ? _operation : other: second ? requestHash : 'b' * 64
                },
                'next_cursor': second ? null : 'page-2',
              }),
              200);
        }
        if (request.url.path == '/api/operations/$_operation' &&
            !request.url.hasQuery) {
          snapshots++;
          return http.Response(jsonEncode(_snapshot('running')), 200);
        }
        if (request.url.path == '/api/operations/$_operation/events') {
          watches++;
          return http.Response('id: 2\nevent: terminal\ndata: [DONE]\n\n', 200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client,
        sessionStore: _store('page-', requestHash));
    addTearDown(rowan.dispose);

    expect(await rowan.recoverFromSession(), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(rowan.snapshot?.operationRef, _operation);
    expect((posts, lists, snapshots, watches), (0, 2, 1, 1));
    client.close();
  });
}
