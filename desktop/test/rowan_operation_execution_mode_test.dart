import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/models/agent_execution_mode.dart';
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

Map<String, Object?> _snapshot(String state) => {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'state': state,
      'can_cancel': false,
      'terminal_event_ref': null,
      'result_sha256': null,
    };

JourneySessionStore _store(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return JourneySessionStore(
    file: File('${directory.path}${Platform.pathSeparator}session.json'),
  )..save(JourneySession(journeyRef: _journey, lens: JourneyLens.verify));
}

void main() {
  testWidgets('native CLI mode sends CLI shape and omits API-only fields',
      (tester) async {
    Map<String, Object?>? prepared;
    Map<String, dynamic>? dispatched;
    final store = _store('rowan-cli-mode-');
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') {
          dispatched = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
              'id: 1\nevent: snapshot\ndata: ${jsonEncode(_snapshot('running'))}\n\n',
              200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client, sessionStore: store)
      ..setExecutionMode(AgentExecutionMode.nativeCliSession)
      ..setEndpoint('claude-cli')
      ..setModel('fixture-model-exact')
      ..setWorkspaceRoot(r'C:\fixture\workspace')
      ..setToolProtocol(AgentToolProtocol.native)
      ..setMaxStepsOverride(4)
      ..setMaxTokens(4096)
      ..setTimeoutSeconds(60)
      ..setAllowWrite(true)
      ..setAllowExec(true);
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (_, operation, __, dispatch) async {
      prepared = Map<String, Object?>.from(operation.operation);
      return dispatch(operation.finalBody(
          const GatewayJourneyBinding(_journey, _head), _grant));
    });

    expect((await rowan.start(context, 'Read fixture.txt')).value, isTrue);
    await tester.pump();

    for (final body in [prepared!, dispatched!]) {
      expect(body['execution_mode'], 'native_cli_session');
      expect(body['endpoint'], 'claude-cli');
      expect(body['model'], 'fixture-model-exact');
      expect(body['root'], r'C:\fixture\workspace');
      expect(body['max_steps'], 4);
      expect(body['timeout_s'], 60);
      expect(body['allow_write'], isTrue);
      expect(body['allow_exec'], isFalse);
      expect(body['stream'], isTrue);
      expect(body.containsKey('tool_protocol'), isFalse);
      expect(body.containsKey('max_tokens'), isFalse);
      expect(body.containsKey('effort'), isFalse);
    }
    expect(store.load()?.operationExecutionMode, 'native_cli_session');
    client.close();
  });

  testWidgets('Codex CLI native mode is blocked before grant review',
      (tester) async {
    var authorized = 0, posts = 0;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent') posts++;
        return http.Response('{}', 500);
      }),
    );
    final rowan = RowanOperationController(client)
      ..setExecutionMode(AgentExecutionMode.nativeCliSession)
      ..setEndpoint('codex-cli')
      ..setModel('fixture-model-exact')
      ..setWorkspaceRoot(r'C:\fixture\workspace');
    addTearDown(rowan.dispose);
    final context = await _mount(tester, (_, __, ___, ____) async {
      authorized += 1;
      return const GatewayAuthorizationOutcome.denied();
    });

    final outcome = await rowan.start(context, 'Try Codex CLI');

    expect(outcome.failure?.code, 'AGENT_CLI_PROFILE_UNSUPPORTED');
    expect(rowan.error, 'AGENT_CLI_PROFILE_UNSUPPORTED');
    expect(authorized, 0);
    expect(posts, 0);
    client.close();
  });
}
