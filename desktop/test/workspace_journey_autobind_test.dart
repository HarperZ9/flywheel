import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/agent_execution_mode.dart';
import 'package:flywheel_desktop/models/agent_run_operation.dart';
import 'package:flywheel_desktop/models/agent_tool_protocol.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/effort_dial.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'journey_controller_test.dart';

const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  testWidgets('agent.run auto-binds existing Journey instead of JOURNEY_REQUIRED',
      (tester) async {
    final api = ScriptedJourneyApi()
      ..reply('list', [projection()])
      ..reply(resumeA, projection());
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    await harness.controller.initialize();
    expect(harness.controller.state.projection, isNull);

    final op = agentRunOperation(
      requestId: 'req-autobind-1',
      goal: 'Fix unit test',
      endpoint: 'openai',
      model: 'gpt-5',
      root: r'C:\work\repo',
      executionMode: AgentExecutionMode.api,
      effort: EffortLevel.standard,
      maxSteps: 4,
      maxTokens: null,
      timeoutSeconds: 60,
      allowWrite: false,
      allowExec: false,
      toolProtocol: AgentToolProtocol.compatibility,
    );
    final preparedBodies = <Map<String, Object?>>[];
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/gateway-grants/prepare/agent.run') {
          final body = jsonDecode(request.body) as Map<String, Object?>;
          preparedBodies.add(body);
          return http.Response(jsonEncode(_agentProposal(body, op)), 200);
        }
        if (request.url.path == '/api/gateway-grants/approve-once') {
          return http.Response(
            jsonEncode({
              'schema': 'flywheel.operation-grant-approval/v1',
              'grant_ref': _grant,
              'expires_at': '2026-08-15T12:00:00Z',
            }),
            200,
          );
        }
        fail('unexpected ${request.method} ${request.url.path}');
      }),
    );
    final grants = GatewayOperationController(GatewayGrantClient(client));

    var dispatched = false;
    GatewayAuthorizationOutcome<Object?>? outcome;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: journeyGatewayAuthorizer(grants, harness.controller),
        child: Scaffold(
          body: Builder(builder: (context) {
            return FilledButton(
              onPressed: () async {
                outcome = await authorizeGatewayOperationDetailed<Object?>(
                  context,
                  op,
                  (_) async {
                    dispatched = true;
                    return true;
                  },
                  currentOperation: () => op,
                );
              },
              child: const Text('Start'),
            );
          }),
        ),
      ),
    ));

    await tester.tap(find.text('Start'));
    await tester.pumpAndSettle();
    expect(find.text('Approve once'), findsOneWidget);
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();

    expect(dispatched, isTrue);
    expect(outcome?.value, isTrue);
    expect(harness.controller.state.projection?.journeyRef, journeyA);
    expect(preparedBodies.single['journey_ref'], journeyA);
    client.close();
  });

  test('ensureWorkspaceJourney creates default Journey when none exist',
      () async {
    final api = ScriptedJourneyApi()
      ..reply('list', const [])
      ..reply('prepare', proposal('create'))
      ..reply('approve', approval())
      ..reply('create', acknowledgement(journeyRef: journeyA, head: headA))
      ..reply(resumeA, projection());
    final harness = ControllerHarness(api);
    addTearDown(harness.dispose);
    await harness.controller.initialize();
    expect(harness.controller.state.projection, isNull);

    final ok = await harness.controller.ensureWorkspaceJourney(
      goal: 'Start coding',
      intakeRef: 'workspace-default',
    );
    expect(ok, isTrue);
    expect(harness.controller.state.activeJourneyRef, journeyA);
    expect(harness.controller.state.projection?.eventHeadSha256, headA);
  });
}

Map<String, Object?> _agentProposal(
        Map<String, Object?> prepare, GatewayOperation op) =>
    {
      'schema': 'flywheel.gateway-grant-proposal/v1',
      'proposal_ref': _proposal,
      'planned_grant_ref': _grant,
      'action': 'agent.run',
      'journey_ref': prepare['journey_ref'],
      'expected_event_head': prepare['expected_event_head'],
      'client_request_id': prepare['client_request_id'],
      'destination': {
        'kind': op.destination.kind,
        'ref': op.destination.ref,
      },
      'tool': op.tool,
      'operation_sha256': headA,
      'arguments_sha256': headA,
      'scopes': op.scopes,
      'data_refs': const [],
      'credential_refs': const [],
      'expires_at': '2026-08-15T12:02:00Z',
      'summary': {
        'schema': 'flywheel.gateway-grant-summary/v1',
        'action': 'agent.run',
        'journey_ref': prepare['journey_ref'],
        'expected_event_head': prepare['expected_event_head'],
        'destination': {
          'kind': op.destination.kind,
          'ref': op.destination.ref,
        },
        'tool': op.tool,
        'operation_sha256': headA,
        'arguments_sha256': headA,
        'scopes': op.scopes,
        'data_refs': const [],
        'credential_refs': const [],
        'effect': 'one dispatch after approval',
        'expires_at': '2026-08-15T12:02:00Z',
      },
    };
