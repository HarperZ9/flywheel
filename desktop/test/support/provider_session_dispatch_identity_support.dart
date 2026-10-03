import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const dispatchIdA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const dispatchShaA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const dispatchOperationA = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const dispatchOperationB = 'op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const dispatchJourneyBinding =
    GatewayJourneyBinding('jrn_$dispatchIdA', dispatchShaA);

Widget dispatchIdentityHost(
  Widget child,
  JourneyController journey,
  GatewayOperationAuthorizer authorize,
) =>
    MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: GatewayOperationScope(
          authorize: authorize,
          journey: journey,
          child: child,
        ),
      ),
    );

GatewayClient dispatchIdentityClient(
  Future<http.Response?> Function(http.Request) handler,
) =>
    GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == providerSessionBindingPath) {
          return http.Response(jsonEncode(dispatchBindingJson()), 200);
        }
        final handled = await handler(request);
        if (handled != null) return handled;
        return http.Response('{}', 404);
      }),
    );

Map<String, Object?> dispatchBindingJson() => {
      'schema': 'flywheel.provider-session-runtime-binding/v1',
      'provider': 'codex',
      'owner_ref': 'owner_$dispatchIdA',
      'journey_ref': dispatchJourneyBinding.journeyRef,
      'workspace_ref': 'workspace-a',
      'model': 'codex:gpt-5.5',
      'permission_scope_sha256': dispatchShaA,
      'config_digest': dispatchShaA,
      'capability_digest': dispatchShaA,
      'provider_binding_ref': 'psb_$dispatchIdA',
      'admitted': true,
      'reason': 'admitted',
      'limitations': const [],
      'runtime_kind': 'fake',
      'observed_at_event_head': dispatchJourneyBinding.eventHead,
    };

Map<String, dynamic> dispatchProgress({
  required String operationRef,
  required String nativeThreadId,
  required String lastProviderEventId,
  String phase = 'provider_event',
  String historyStatus = 'complete',
  String sideEffectStatus = 'input_sent',
  String reason = 'observed',
}) =>
    {
      'provider_session': {
        'phase': phase,
        'provider': 'codex',
        'operation_ref': operationRef,
        'native_session_id': 'session-$dispatchIdA',
        'native_thread_id': nativeThreadId,
        'native_turn_id': 'turn-$dispatchIdA',
        'last_provider_event_id': lastProviderEventId,
        'history_status': historyStatus,
        'side_effect_status': sideEffectStatus,
        'reason': reason,
      }
    };

Future<JourneyController> dispatchJourney() async {
  final directory = Directory.systemTemp.createTempSync('desktop-rereview-');
  final controller = JourneyController(
    api: const _DispatchJourneyApi(),
    draftStore: JourneyDraftStore(file: File('${directory.path}/drafts.json')),
    sessionStore:
        JourneySessionStore(file: File('${directory.path}/session.json'))
          ..save(JourneySession(
              journeyRef: dispatchJourneyBinding.journeyRef,
              lens: JourneyLens.verify)),
  );
  await controller.initialize();
  return controller;
}

String dispatchTerminalSse(String action) {
  final result = OperationResult.fromJson({
    'schema': operationResultSchema,
    'operation_ref': dispatchOperationA,
    'action': action,
    'state': 'completed',
    'result': {
      'provider_session': {
        'provider': 'codex',
        'native_thread_id': 'thread-terminal',
        'config_digest': dispatchShaA,
      },
      'history_status': 'complete',
      'side_effect_status': 'input_sent',
    },
  });
  final terminal = {
    'snapshot': {
      'schema': operationSnapshotSchema,
      'operation_ref': dispatchOperationA,
      'journey_ref': dispatchJourneyBinding.journeyRef,
      'event_head_sha256': dispatchJourneyBinding.eventHead,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': dispatchShaA,
      'result_sha256': result.canonicalSha256,
    },
    'result': result.toJson(),
  };
  return 'id: 1\r\nevent: terminal\r\ndata: ${jsonEncode(terminal)}\r\n\r\n'
      'id: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';
}

class _DispatchJourneyApi implements JourneyApi {
  const _DispatchJourneyApi();

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
      'journey_ref': dispatchJourneyBinding.journeyRef,
      'event_head_sha256': dispatchJourneyBinding.eventHead,
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
