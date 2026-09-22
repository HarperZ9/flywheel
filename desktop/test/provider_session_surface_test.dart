import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/controllers/provider_session_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/provider_session_surface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _providerBinding = 'psb_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', _sha);

Widget _host(Widget child, JourneyController journey) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: GatewayOperationScope(
          authorize: (_, operation, currentOperation, dispatch) {
            if (currentOperation() != operation) return Future.value();
            return dispatch(operation.finalBody(_binding, 'gnt_$_a'));
          },
          journey: journey,
          child: child,
        ),
      ),
    );

void main() {
  testWidgets('missing binding read keeps native send disabled',
      (tester) async {
    final controller = ProviderSessionController();
    final journey = await _journey();
    addTearDown(controller.dispose);
    addTearDown(journey.dispose);
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async => http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-transport-error/v1',
              'error': {'code': 'NOT_FOUND', 'message': 'not found'},
            }),
            404,
          )),
    );
    addTearDown(client.close);

    await tester.pumpWidget(_host(
        ProviderSessionSurface(
          client: client,
          controller: controller,
          provider: 'codex',
          draft: 'hello',
          workspaceRef: 'workspace-a',
          onProviderChanged: (_) {},
          onDraftChanged: (_) {},
        ),
        journey));
    await tester.pumpAndSettle();

    expect(find.textContaining('Binding unavailable'), findsOneWidget);
    final send = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Send turn'));
    expect(send.onPressed, isNull);
  });

  testWidgets('native send uses fetched binding and provider path',
      (tester) async {
    final controller = ProviderSessionController();
    final journey = await _journey();
    addTearDown(controller.dispose);
    addTearDown(journey.dispose);
    Map<String, dynamic>? captured;
    Map<String, dynamic>? bindingRequest;
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == providerSessionBindingPath) {
          expect(request.method, 'POST');
          bindingRequest = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_bindingJson()), 200);
        }
        if (request.url.path == providerSessionTurnPath) {
          captured = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(_terminalSse(), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);

    await tester.pumpWidget(_host(
        ProviderSessionSurface(
          client: client,
          controller: controller,
          provider: 'codex',
          draft: 'hello native',
          workspaceRef: 'workspace-a',
          selectedModel: 'codex:gpt-5.5',
          onProviderChanged: (_) {},
          onDraftChanged: (_) {},
        ),
        journey));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Send turn'));
    await tester.pumpAndSettle();

    expect(bindingRequest?['schema'], providerSessionBindingRequestSchema);
    expect(bindingRequest?['journey_ref'], _binding.journeyRef);
    expect(bindingRequest?['expected_event_head'], _binding.eventHead);
    expect(bindingRequest?['provider'], 'codex');
    expect(bindingRequest?['workspace_ref'], 'workspace-a');
    expect(bindingRequest?['model'], 'codex:gpt-5.5');
    expect(bindingRequest?['permission_scope'], isA<Map>());
    expect(captured?['workspace_ref'], 'workspace-a');
    expect(captured?['config_digest'], _sha);
    expect(captured?['capability_digest'], _sha);
    expect(captured?['provider_binding_ref'], _providerBinding);
    expect(captured?['model'], 'codex:gpt-5.5');
    expect(captured?['input'], [
      {'type': 'input_text', 'text': 'hello native'}
    ]);
  });
}

Map<String, Object?> _bindingJson({
  bool admitted = true,
  String workspaceRef = 'workspace-a',
  String model = 'codex:gpt-5.5',
  String configDigest = _sha,
  String capabilityDigest = _sha,
  String providerBindingRef = _providerBinding,
}) =>
    {
      'schema': 'flywheel.provider-session-runtime-binding/v1',
      'provider': 'codex',
      'owner_ref': 'owner_$_a',
      'journey_ref': _binding.journeyRef,
      'workspace_ref': workspaceRef,
      'model': model,
      'permission_scope_sha256': _sha,
      'config_digest': configDigest,
      'capability_digest': capabilityDigest,
      'provider_binding_ref': providerBindingRef,
      'admitted': admitted,
      'reason': admitted ? 'admitted' : 'AGENT_NATIVE_RUNTIME_DISABLED',
      'limitations': const [],
      'runtime_kind': admitted ? 'fake' : 'disabled',
      'observed_at_event_head': _binding.eventHead,
    };

Future<JourneyController> _journey() async {
  final directory = Directory.systemTemp.createTempSync('provider-surface-');
  final api = _JourneyApi();
  final controller = JourneyController(
    api: api,
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

String _terminalSse() {
  final result = OperationResult.fromJson({
    'schema': operationResultSchema,
    'operation_ref': _operation,
    'action': providerSessionTurnAction,
    'state': 'completed',
    'result': {
      'provider_session': {
        'provider': 'codex',
        'native_thread_id': 'thread-1',
        'config_digest': _sha,
      },
      'history_status': 'complete',
      'side_effect_status': 'input_sent',
    },
  });
  final terminal = {
    'snapshot': {
      'schema': operationSnapshotSchema,
      'operation_ref': _operation,
      'journey_ref': 'jrn_$_a',
      'event_head_sha256': _sha,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': _sha,
      'result_sha256': result.canonicalSha256,
    },
    'result': result.toJson(),
  };
  return 'id: 1\r\nevent: terminal\r\ndata: ${jsonEncode(terminal)}\r\n\r\n'
      'id: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';
}
