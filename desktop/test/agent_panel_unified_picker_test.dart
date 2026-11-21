import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/ide/agent_panel.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');
const _grant = 'gnt_$_a';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  testWidgets(
      'AgentPanel unified picker supports claude-cli, codex, and API endpoints',
      (tester) async {
    final goal = TextEditingController(text: 'Check unified picker');
    addTearDown(goal.dispose);
    Map<String, Object?>? prepared;
    Map<String, dynamic>? dispatched;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
            jsonEncode({
              'rows': [
                {
                  'name': 'openrouter',
                  'backend': 'openai',
                  'credential': 'present',
                  'provider_role': '',
                  'configured': true,
                },
                {
                  'name': 'anthropic',
                  'backend': 'anthropic',
                  'credential': 'present',
                  'provider_role': '',
                  'configured': true,
                },
                {
                  'name': 'openai',
                  'backend': 'openai',
                  'credential': 'present',
                  'provider_role': '',
                  'configured': true,
                },
                {
                  'name': 'ollama',
                  'backend': 'local',
                  'credential': 'present',
                  'provider_role': '',
                  'configured': true,
                },
                {
                  'name': 'claude-cli',
                  'backend': 'native-cli',
                  'credential': 'own-cli-auth',
                  'provider_role': '',
                  'configured': true,
                },
                {
                  'name': 'codex',
                  'backend': 'native-cli',
                  'credential': 'own-cli-auth',
                  'provider_role': '',
                  'configured': true,
                },
              ],
            }),
            200,
          );
        }
        if (request.url.path == '/api/models') {
          final ep = request.url.queryParameters['endpoint'] ?? 'codex';
          return http.Response(
            jsonEncode({
              'endpoint': ep,
              'models': [
                {'id': '$ep-model-1', 'default': false},
              ],
              'reason': '',
            }),
            200,
          );
        }
        if (request.url.path == '/api/agent') {
          dispatched = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            'id: 1\nevent: snapshot\ndata: ${jsonEncode({
                  'schema': operationSnapshotSchema,
                  'operation_ref': _operation,
                  'journey_ref': _binding.journeyRef,
                  'event_head_sha256': 'b' * 64,
                  'state': 'running',
                  'can_cancel': false,
                  'terminal_event_ref': null,
                  'result_sha256': null,
                })}\n\n',
            200,
          );
        }
        return http.Response('{}', 404);
      }),
    );

    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (_, operation, __, dispatch) async {
          prepared = Map<String, Object?>.from(operation.operation);
          return dispatch(operation.finalBody(_binding, _grant));
        },
        child: Scaffold(
          body: AgentPanel(
            client: client,
            alive: true,
            workspaceRoot: r'C:\work\repo',
            goalController: goal,
            onRunStarted: () {},
            onRunFinished: () {},
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // API mode exposes API endpoints (openrouter, anthropic, openai, ollama).
    await tester.tap(find.byKey(const Key('agent-endpoint-picker')));
    await tester.pumpAndSettle();
    expect(find.text('openrouter'), findsWidgets);
    expect(find.text('anthropic'), findsWidgets);
    expect(find.text('openai'), findsWidgets);
    expect(find.text('ollama'), findsWidgets);
    await tester.tap(find.text('anthropic').last);
    await tester.pumpAndSettle();

    // Native CLI mode exposes both claude-cli and codex.
    await tester.tap(find.byKey(const Key('agent-execution-mode')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('native CLI session').last);
    await tester.pumpAndSettle();
    expect(
      find.textContaining('Official CLI-owned auth (claude-cli, codex)'),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('agent-endpoint-picker')));
    await tester.pumpAndSettle();
    expect(find.text('claude-cli (CLI)'), findsWidgets);
    expect(find.text('codex (CLI)'), findsWidgets);
    await tester.tap(find.text('codex (CLI)').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('default model'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('codex-model-1'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run'));
    await tester.pump();

    for (final body in [prepared!, dispatched!]) {
      expect(body['execution_mode'], 'native_cli_session');
      expect(body['endpoint'], 'codex');
      expect(body['model'], 'codex-model-1');
      expect(body['allow_exec'], isFalse);
    }
    client.close();
  });
}
