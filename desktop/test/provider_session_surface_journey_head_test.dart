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
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/provider_session_surface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _bindingA = GatewayJourneyBinding('jrn_$_a', _shaA);

Widget _host(Widget child, JourneyController journey) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: GatewayOperationScope(
          authorize: (_, operation, currentOperation, dispatch) {
            final current = currentOperation();
            if (current == null || current != operation) return Future.value();
            return dispatch(operation.finalBody(_bindingA, 'gnt_$_a'));
          },
          journey: journey,
          child: child,
        ),
      ),
    );

void main() {
  testWidgets('journey head drift disables the current native binding',
      (tester) async {
    // Break this catches: a binding admitted at event head A stays actionable
    // after the visible Journey scope advances to event head B.
    final controller = ProviderSessionController();
    final journeyA = await _journey(_shaA);
    final journeyB = await _journey(_shaB);
    addTearDown(controller.dispose);
    addTearDown(journeyA.dispose);
    addTearDown(journeyB.dispose);
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == providerSessionBindingPath) {
          return http.Response(jsonEncode(_bindingJson()), 200);
        }
        if (request.url.path == providerSessionTurnPath) {
          return http.Response('{}', 500);
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(client.close);
    final surface = ProviderSessionSurface(
      client: client,
      controller: controller,
      provider: 'codex',
      draft: 'hello native',
      workspaceRef: 'workspace-a',
      selectedModel: 'codex:gpt-5.5',
      onProviderChanged: (_) {},
      onDraftChanged: (_) {},
    );

    await tester.pumpWidget(_host(surface, journeyA));
    await tester.pumpAndSettle();
    await tester.pumpWidget(_host(surface, journeyB));
    await tester.pumpAndSettle();

    final send = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Send turn'));
    expect(send.onPressed, isNull);
  });
}

Map<String, Object?> _bindingJson() => {
      'schema': 'flywheel.provider-session-runtime-binding/v1',
      'provider': 'codex',
      'owner_ref': 'owner_$_a',
      'journey_ref': _bindingA.journeyRef,
      'workspace_ref': 'workspace-a',
      'model': 'codex:gpt-5.5',
      'permission_scope_sha256': _shaA,
      'config_digest': _shaA,
      'capability_digest': _shaA,
      'provider_binding_ref': 'psb_$_a',
      'admitted': true,
      'reason': 'admitted',
      'limitations': const [],
      'runtime_kind': 'fake',
      'observed_at_event_head': _bindingA.eventHead,
    };

Future<JourneyController> _journey(String eventHead) async {
  final directory = Directory.systemTemp.createTempSync('provider-head-');
  final controller = JourneyController(
    api: _JourneyApi(eventHead),
    draftStore: JourneyDraftStore(file: File('${directory.path}/drafts.json')),
    sessionStore:
        JourneySessionStore(file: File('${directory.path}/session.json'))
          ..save(JourneySession(
              journeyRef: _bindingA.journeyRef, lens: JourneyLens.verify)),
  );
  await controller.initialize();
  return controller;
}

class _JourneyApi implements JourneyApi {
  final String eventHead;

  const _JourneyApi(this.eventHead);

  @override
  Future<List<JourneySummary>> list() async => [_projection(eventHead)];
  @override
  Future<JourneyProjection> resume(String journeyRef, JourneyLens lens) async =>
      _projection(eventHead);
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

JourneyProjection _projection(String eventHead) => JourneyProjection.fromJson({
      'schema': 'flywheel.evidence-journey-projection/v2',
      'journey_ref': _bindingA.journeyRef,
      'event_head_sha256': eventHead,
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
