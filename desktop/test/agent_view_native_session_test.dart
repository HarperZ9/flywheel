import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', _sha);

const _roster =
    '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';

Widget _host(Widget child, {JourneyController? journey}) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: GatewayOperationScope(
          authorize: (_, __, ___, ____) => Future.value(),
          journey: journey,
          child: child,
        ),
      ),
    );

void main() {
  testWidgets('agent mode swaps panes and back', (tester) async {
    await tester.pumpWidget(_host(AgentView(
      client: GatewayClient(),
      alive: true,
      settings: DesktopSettings(),
    )));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsNothing);
    await tester.tap(find.text('agent'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsOneWidget);
    expect(find.text('every run persists with its trace'), findsOneWidget);
    await tester.tap(find.text('chat'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsNothing);
  });

  testWidgets('native session mode preserves its Journey draft',
      (tester) async {
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(_roster, 200);
        }
        if (request.url.path == '/api/provider-sessions/binding') {
          return http.Response(
              '{"schema":"flywheel.evidence-transport-error/v1",'
              '"error":{"code":"NOT_FOUND","message":"not found"}}',
              404);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);

    await tester.pumpWidget(_host(AgentView(
      client: client,
      alive: true,
      settings: DesktopSettings(),
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.text('native'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'native draft');
    await tester.pump();
    await tester.tap(find.text('agent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('native'));
    await tester.pumpAndSettle();

    expect(find.text('Provider native session'), findsOneWidget);
    expect(_editorText(tester), 'native draft');
  });

  testWidgets('native session mode does not use chat endpoint as model',
      (tester) async {
    // Break this catches: entering native mode with a default chat endpoint
    // sends endpoint alias `codex-cli` as the provider-session model.
    final journey = await _journey();
    addTearDown(journey.dispose);
    Map<String, dynamic>? bindingRequest;
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
              jsonEncode({
                'rows': [
                  {
                    'name': 'codex-cli',
                    'backend': 'codex-cli',
                    'credential': 'cli-auth',
                    'provider_role': '',
                    'configured': true,
                    'account_required': true,
                    'account_authenticated': true,
                  }
                ]
              }),
              200);
        }
        if (request.url.path == '/api/models') {
          return http.Response('{"models":[]}', 200);
        }
        if (request.url.path == providerSessionBindingPath) {
          bindingRequest = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
              jsonEncode({
                'schema': 'flywheel.provider-session-runtime-binding/v1',
                'provider': 'codex',
                'owner_ref': 'owner_$_a',
                'journey_ref': _binding.journeyRef,
                'workspace_ref': bindingRequest?['workspace_ref'],
                'model': bindingRequest?['model'] ?? '',
                'permission_scope_sha256': _sha,
                'config_digest': _sha,
                'capability_digest': _sha,
                'provider_binding_ref': 'psb_$_a',
                'admitted': true,
                'reason': 'admitted',
                'limitations': const [],
                'runtime_kind': 'fake',
                'observed_at_event_head': _binding.eventHead,
              }),
              200);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);

    await tester.pumpWidget(_host(
      AgentView(
        client: client,
        alive: true,
        settings:
            DesktopSettings(recentWorkspaces: ['C:/dev/workspaces/native-a']),
      ),
      journey: journey,
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('native'));
    await tester.pumpAndSettle();

    expect(bindingRequest, isNotNull);
    expect(bindingRequest!.containsKey('model'), isFalse);
  });
}

String _editorText(WidgetTester tester) =>
    tester.widget<TextField>(find.byType(TextField)).controller!.text;

Future<JourneyController> _journey() async {
  final directory = Directory.systemTemp.createTempSync('agent-native-');
  final controller = JourneyController(
    api: _JourneyApi(),
    draftStore: JourneyDraftStore(file: File('${directory.path}/drafts.json')),
    sessionStore:
        JourneySessionStore(file: File('${directory.path}/session.json'))
          ..save(JourneySession(
              journeyRef: _binding.journeyRef, lens: JourneyLens.verify)),
  );
  await controller.initialize();
  return controller;
}

class _JourneyApi implements JourneyApi {
  @override
  Future<List<JourneySummary>> list() async => [_projection()];
  @override
  Future<JourneyProjection> resume(String journeyRef, JourneyLens lens) async =>
      _projection();
  @override
  Future<GrantRef> approveGrantOnce(String proposalRef) async =>
      throw UnimplementedError();
  @override
  Future<JourneyCancelResult> cancel(JourneyCancelRequest request) async =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> append(JourneyAppendRequest request) async =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> check(JourneyCheckRequest request) async =>
      throw UnimplementedError();
  @override
  Future<JourneyMutationAck> create(JourneyCreateRequest request) async =>
      throw UnimplementedError();
  @override
  Future<JourneyExportResult> export(JourneyExportRequest request) async =>
      throw UnimplementedError();
  @override
  Future<GrantProposal> prepareGrant(GrantIntent intent) async =>
      throw UnimplementedError();
}

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
      'next_actions': const [],
      'detail': 'Ready',
      'lens': 'Verify',
    });
