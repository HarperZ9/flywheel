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
  testWidgets('AgentPanel sends native tool protocol only when selected',
      (tester) async {
    final goal = TextEditingController(text: 'Use the native bridge');
    addTearDown(goal.dispose);
    Map<String, Object?>? prepared;
    Map<String, dynamic>? dispatched;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
              '{"rows":[{"name":"local","backend":"local","credential":"local-none","provider_role":"","configured":true}]}',
              200);
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
              200);
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

    await tester.tap(find.text('compatibility'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('native').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run'));
    await tester.pump();

    expect(prepared?['tool_protocol'], 'native');
    expect(dispatched?['tool_protocol'], 'native');
    expect(dispatched?['root'], r'C:\work\repo');
    client.close();
  });

  testWidgets('AgentPanel native CLI mode sends CLI body without API budgets',
      (tester) async {
    final goal = TextEditingController(text: 'Read fixture.txt');
    addTearDown(goal.dispose);
    Map<String, Object?>? prepared;
    Map<String, dynamic>? dispatched;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
              '{"rows":[{"name":"claude-cli","backend":"native-cli","credential":"own-cli-auth","provider_role":"","configured":true},{"name":"codex-cli","backend":"native-cli","credential":"own-cli-auth","provider_role":"","configured":true}]}',
              200);
        }
        if (request.url.path == '/api/models') {
          return http.Response(
              '{"endpoint":"claude-cli","models":[{"id":"fixture-model-exact","default":false}],"reason":""}',
              200);
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
              200);
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

    await tester.tap(find.byKey(const Key('agent-execution-mode')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('native CLI session').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Codex CLI unavailable'), findsOneWidget);
    expect(find.textContaining('output tokens unsupported'), findsOneWidget);

    await tester.tap(find.text('default model'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('fixture-model-exact'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run'));
    await tester.pump();

    for (final body in [prepared!, dispatched!]) {
      expect(body['execution_mode'], 'native_cli_session');
      expect(body['endpoint'], 'claude-cli');
      expect(body['model'], 'fixture-model-exact');
      expect(body['root'], r'C:\work\repo');
      expect(body['allow_exec'], isFalse);
      expect(body.containsKey('tool_protocol'), isFalse);
      expect(body.containsKey('max_tokens'), isFalse);
      expect(body.containsKey('effort'), isFalse);
    }
    client.close();
  });
}
