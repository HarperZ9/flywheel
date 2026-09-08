import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/ide/agent_panel.dart';
import 'package:flywheel_desktop/models/continuation_models.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/projects_view.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', _sha);
const _approval = {
  'schema': 'flywheel.operation-grant-approval/v1',
  'grant_ref': 'gnt_$_a',
  'expires_at': '2026-09-08T12:02:00Z',
};
const _previewRef = 'cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _done =
    'id: 1\r\nevent: terminal\r\ndata: {"snapshot":{"schema":"flywheel.gateway-operation-snapshot/v1","operation_ref":"op_$_a","journey_ref":"jrn_$_a","event_head_sha256":"$_sha","state":"completed","can_cancel":false,"terminal_event_ref":"$_sha","result_sha256":"4e19f40df36fb27f1fa438e0320c339c1decfe2866d8b31b3daa34a918d3bb94"},"result":{"schema":"flywheel.gateway-operation-result/v1","operation_ref":"op_$_a","action":"agent.run","state":"completed","result":{"final":"done"}}}\r\n\r\nid: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';

Map<String, Object?> _proposal(Map<String, dynamic> body) {
  final operation = body['operation'] as Map<String, dynamic>;
  final shared = {
    'action': 'agent.run',
    'journey_ref': body['journey_ref'],
    'expected_event_head': body['expected_event_head'],
    'destination': {'kind': 'endpoint', 'ref': operation['endpoint']},
    'tool': 'agent.run',
    'operation_sha256': _sha,
    'arguments_sha256': _sha,
    'scopes': ['network'],
    'data_refs': operation['data_refs'],
    'credential_refs': operation['credential_refs'],
    'expires_at': '2026-09-08T12:02:00Z',
  };
  return {
    'schema': 'flywheel.gateway-grant-proposal/v1',
    'proposal_ref': 'prp_$_a',
    'planned_grant_ref': 'gnt_$_a',
    ...shared,
    'client_request_id': body['client_request_id'],
    'summary': {
      'schema': 'flywheel.gateway-grant-summary/v1',
      ...shared,
      'effect': 'one dispatch after approval',
    },
  };
}

Map<String, Object?> _previewJson() => {
      'schema': 'flywheel.native-continuation-preview/v1',
      'preview_ref': _previewRef,
      'preview_sha256': _sha,
      'source_state_sha256': _sha,
      'intake_ref': 'continuation/$_previewRef.intake.json',
      'source': {'root': r'C:\work\repo', 'export_path': null},
      'repo': {'branch': 'main', 'head': _sha, 'dirty_files': const []},
      'import': {
        'mappings': const [],
        'dropped': const [],
        'mcp_server_count': 0,
      },
      'export': {'signals': const []},
      'context_package': {
        'selected_tasks': ['Fix the parser'],
        'selected_summaries': const [],
        'selected_files': ['lib/parser.dart'],
        'commits': const [],
      },
      'runner_context': {
        'schema': 'flywheel.native-continuation-runner-context/v1',
        'root': r'C:\work\repo',
        'goal': 'Private runner prompt',
        'selected_files': ['lib/parser.dart'],
      },
      'provider_native_resume': {
        'state': 'unavailable',
        'reason': 'provider-native resume is not claimed',
      },
      'health': {'state': 'ready', 'blocking_omissions': const []},
      'omissions': const [],
    };

Map<String, Object?> _startJson() => {
      'schema': 'flywheel.native-continuation-start/v1',
      'preview_ref': _previewRef,
      'open_lens': 'Rescue',
      'journey': {
        'schema': 'flywheel.evidence-journey-mutation-ack/v2',
        'journey_ref': _binding.journeyRef,
        'event_head_sha256': _binding.eventHead,
        'event_sha256': _binding.eventHead,
        'projection_sha256': _sha,
        'idempotent_replay': false,
      },
    };

Map<String, Object?> _privateContextJson() => {
      'schema': 'flywheel.native-continuation-private-context/v1',
      'preview_ref': _previewRef,
      'source_state_sha256': _sha,
      'context_package': {
        'selected_tasks': ['Fix the parser'],
        'selected_files': ['lib/parser.dart'],
      },
      'runner_context': {
        'schema': 'flywheel.native-continuation-runner-context/v1',
        'root': r'C:\work\repo',
        'goal': 'Private runner prompt',
        'selected_files': ['lib/parser.dart'],
      },
    };

JourneyProjection _projection() => JourneyProjection.fromJson({
      'schema': 'flywheel.evidence-journey-projection/v2',
      'journey_ref': _binding.journeyRef,
      'event_head_sha256': _binding.eventHead,
      'fact_ids': const [],
      'claim_ids': const [],
      'checks': const [],
      'verdicts': const {},
      'missing_evidence': const [],
      'stage': 'running',
      'conclusion': null,
      'next_actions': [
        {
          'action_id': 'continue-$_previewRef',
          'kind': 'repair',
          'description': 'Open the private context.',
          'basis_refs': [_previewRef],
        },
      ],
      'detail': 'Accepted server detail',
      'lens': 'Rescue',
    });

class _JourneyApi implements JourneyApi {
  final calls = <String>[];
  @override
  Future<List<JourneySummary>> list() async => const [];
  @override
  Future<JourneyProjection> resume(String journeyRef, JourneyLens lens) async {
    calls.add('resume:$journeyRef:${lens.name}');
    return _projection();
  }

  @override
  Future<GrantProposal> prepareGrant(GrantIntent intent) =>
      throw UnimplementedError();
  @override
  Future<GrantRef> approveGrantOnce(String proposalRef) =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> create(JourneyCreateRequest request) =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> append(JourneyAppendRequest request) =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> check(JourneyCheckRequest request) =>
      throw UnimplementedError();
  @override
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request) =>
      throw UnimplementedError();
  @override
  Future<JourneyExportResult> export(JourneyExportRequest request) =>
      throw UnimplementedError();
}

Directory _temporary(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

void main() {
  testWidgets('AgentPanel grants and dispatches continuation-bound agent.run', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 700));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final handoff = {
      'schema': continuationAgentHandoffSchema,
      'preview_ref': 'cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'preview_sha256': _sha,
      'source_state_sha256': _sha,
      'selected_files': ['lib/parser.dart'],
    };
    final goal = TextEditingController(text: 'Private runner prompt');
    addTearDown(goal.dispose);
    Map<String, dynamic>? prepared;
    Map<String, dynamic>? dispatched;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
            '{"rows":[{"name":"local","backend":"local","credential":"local-none","provider_role":"","configured":true}]}',
            200,
          );
        }
        if (request.url.path.contains('/prepare/')) {
          prepared = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_proposal(prepared!)), 200);
        }
        if (request.url.path.endsWith('/approve-once')) {
          return http.Response(jsonEncode(_approval), 200);
        }
        dispatched = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(_done, 200);
      }),
    );
    final controller = GatewayOperationController(GatewayGrantClient(client));
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: flywheelLightTheme(),
        home: GatewayOperationScope(
          authorize: (context, operation, current, dispatch) async {
            final ready = await controller.prepare(
              operation,
              binding: _binding,
              currentOperation: current,
              currentBinding: () => _binding,
            );
            if (!context.mounted || !ready) return null;
            return showOperationGrantSheet<Object?>(
              context,
              controller,
              dispatch,
            );
          },
          child: Scaffold(
            body: AgentPanel(
              client: client,
              alive: true,
              workspaceRoot: r'C:\work\repo',
              goalController: goal,
              continuationHandoff: handoff,
              onRunStarted: () {},
              onRunFinished: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Run'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();

    expect(prepared?['journey_ref'], _binding.journeyRef);
    expect(prepared?['expected_event_head'], _binding.eventHead);
    expect(prepared?['operation']['goal'], 'Private runner prompt');
    expect(prepared?['operation']['root'], r'C:\work\repo');
    expect(prepared?['operation']['continuation'], handoff);
    expect(dispatched?['journey_ref'], _binding.journeyRef);
    expect(dispatched?['root'], r'C:\work\repo');
    expect(dispatched?['continuation'], handoff);
  });

  testWidgets('ProjectsView continuation modal preserves gateway grant scope', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1200, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final directory = _temporary('projects-continuation-handoff-');
    final journeyApi = _JourneyApi();
    final journey = JourneyController(
      api: journeyApi,
      draftStore: JourneyDraftStore(
          file: File('${directory.path}/journey-drafts.json')),
      sessionStore:
          JourneySessionStore(file: File('${directory.path}/session.json')),
    );
    addTearDown(journey.dispose);
    Map<String, dynamic>? prepared;
    Map<String, dynamic>? dispatched;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        switch (request.url.path) {
          case '/api/projects':
            return http.Response('{"projects":[]}', 200);
          case '/api/store':
            return http.Response('{"records":0}', 200);
          case '/api/continuation/preview':
            return http.Response(jsonEncode(_previewJson()), 200);
          case '/api/continuation/start':
            return http.Response(jsonEncode(_startJson()), 200);
          case '/api/continuation/context':
            return http.Response(jsonEncode(_privateContextJson()), 200);
          case '/api/endpoints':
            return http.Response(
              '{"rows":[{"name":"local","backend":"local","credential":"local-none","provider_role":"","configured":true}]}',
              200,
            );
          case '/api/gateway-grants/prepare/agent.run':
            prepared = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(jsonEncode(_proposal(prepared!)), 200);
          case '/api/gateway-grants/approve-once':
            return http.Response(jsonEncode(_approval), 200);
          case '/api/agent':
            dispatched = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(_done, 200);
        }
        return http.Response('{"error":"unexpected"}', 500);
      }),
    );
    final grants = GatewayOperationController(GatewayGrantClient(client));
    addTearDown(grants.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: flywheelLightTheme(),
        home: GatewayOperationScope(
          authorize: (context, operation, current, dispatch) async {
            final ready = await grants.prepare(
              operation,
              binding: _binding,
              currentOperation: current,
              currentBinding: () => _binding,
            );
            if (!context.mounted || !ready) return null;
            return showOperationGrantSheet<Object?>(context, grants, dispatch);
          },
          child: Scaffold(
            body: ProjectsView(client: client, journey: journey, alive: true),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('continuation-root')),
      r'C:\work\repo',
    );
    await tester.tap(find.text('Preview continuation'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Continue with agent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();

    expect(journeyApi.calls, isNotEmpty);
    expect(journeyApi.calls.first, 'resume:${_binding.journeyRef}:rescue');
    expect(
        journeyApi.calls, everyElement('resume:${_binding.journeyRef}:rescue'));
    expect(prepared?['journey_ref'], _binding.journeyRef);
    expect(prepared?['expected_event_head'], _binding.eventHead);
    expect(prepared?['operation']['goal'], 'Private runner prompt');
    expect(prepared?['operation']['root'], r'C:\work\repo');
    expect(prepared?['operation']['continuation'], {
      'schema': continuationAgentHandoffSchema,
      'preview_ref': _previewRef,
      'preview_sha256': _sha,
      'source_state_sha256': _sha,
      'selected_files': ['lib/parser.dart'],
    });
    expect(dispatched?['journey_ref'], _binding.journeyRef);
    expect(dispatched?['continuation'], prepared?['operation']['continuation']);
  });
}
