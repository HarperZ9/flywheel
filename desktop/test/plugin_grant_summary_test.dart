import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _credential = 'cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = {
  'schema': 'flywheel.gateway-grant-proposal/v1',
  'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'action': 'plugin.call',
  'journey_ref': _journey,
  'expected_event_head': _head,
  'client_request_id': 'request-1',
  'destination': {'kind': 'plugin', 'ref': 'gather'},
  'tool': 'find',
  'operation_sha256': _head,
  'arguments_sha256': _head,
  'scopes': ['write', 'exec', 'network', 'plugin', 'secrets'],
  'data_refs': ['data_public_fixture'],
  'credential_refs': [_credential],
  'expires_at': '2026-08-15T12:02:00Z',
  'summary': {
    'schema': 'flywheel.gateway-grant-summary/v1',
    'action': 'plugin.call',
    'journey_ref': _journey,
    'expected_event_head': _head,
    'destination': {'kind': 'plugin', 'ref': 'gather'},
    'tool': 'find',
    'operation_sha256': _head,
    'arguments_sha256': _head,
    'scopes': ['write', 'exec', 'network', 'plugin', 'secrets'],
    'data_refs': ['data_public_fixture'],
    'credential_refs': [_credential],
    'effect': 'one dispatch after approval',
    'expires_at': '2026-08-15T12:02:00Z',
  }
};

GatewayOperation _call() => GatewayOperation.pluginCall(
    name: 'gather',
    tool: 'find',
    arguments: const {},
    dataRefs: const ['data_public_fixture'],
    credentialRefs: const [_credential],
    clientRequestId: 'request-1');

void main() {
  _summaryTest();
  _typedFailureTest();
  _downstreamFailureTest();
}

void _summaryTest() {
  testWidgets('challenge renders destination tool data and credential handles',
      (tester) async {
    final controller = GatewayOperationController(GatewayGrantClient(
        GatewayClient(
            baseUrl: 'https://gateway.invalid',
            httpClient: MockClient(
                (_) async => http.Response(jsonEncode(_proposal), 200)))));
    final operation = _call();
    expect(
        await controller.prepare(operation,
            binding: const GatewayJourneyBinding(_journey, _head),
            currentOperation: () => operation,
            currentBinding: () => const GatewayJourneyBinding(_journey, _head)),
        isTrue);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () =>
              showOperationGrantSheet<void>(context, controller, (_) async {}),
          child: const Text('Open'));
    })));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.textContaining('plugin: gather'), findsOneWidget);
    expect(find.textContaining('Tool: find'), findsOneWidget);
    expect(find.textContaining('data_public_fixture'), findsOneWidget);
    expect(find.textContaining(_credential), findsOneWidget);
  });
}

void _downstreamFailureTest() {
  test('structured downstream failure remains typed and fixed', () async {
    final operation = _call();
    final controller =
        GatewayOperationController(GatewayGrantClient(GatewayClient(
            baseUrl: 'https://gateway.invalid',
            httpClient: MockClient((request) async => http.Response(
                jsonEncode(request.url.path.endsWith('approve-once')
                    ? {
                        'schema': 'flywheel.operation-grant-approval/v1',
                        'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        'expires_at': '2026-08-15T12:02:00Z'
                      }
                    : _proposal),
                200)))));
    await controller.prepare(operation,
        binding: const GatewayJourneyBinding(_journey, _head),
        currentOperation: () => operation,
        currentBinding: () => const GatewayJourneyBinding(_journey, _head));
    final result = await controller
        .approveAndDispatch((_) async => throw GatewayException.fromResponse(
            502,
            jsonEncode({
              'schema': 'flywheel.evidence-transport-error/v1',
              'error': {
                'code': 'EXTERNAL_ACTION_FAILED',
                'message': 'authorized external action failed'
              }
            })));
    expect(result, isNull);
    expect(controller.failure?.code, 'EXTERNAL_ACTION_FAILED');
    expect(controller.failure?.message, 'Authorized external action failed');
  });
}

void _typedFailureTest() {
  testWidgets('head conflict is visible only after refresh', (tester) async {
    var refreshed = false;
    final controller =
        GatewayOperationController(GatewayGrantClient(GatewayClient(
            baseUrl: 'https://gateway.invalid',
            httpClient: MockClient((_) async => http.Response(
                jsonEncode({
                  'schema': 'flywheel.evidence-transport-error/v1',
                  'error': {'code': 'HEAD_CONFLICT', 'message': 'fixed'}
                }),
                409)))));
    final operation = GatewayOperation.pluginProbe(
        name: 'gather', clientRequestId: 'request-1');
    expect(
        await controller.prepare(operation,
            binding: const GatewayJourneyBinding(_journey, _head),
            currentOperation: () => operation,
            currentBinding: () => const GatewayJourneyBinding(_journey, _head),
            refreshOnHeadConflict: () async => refreshed = true),
        isFalse);
    expect(refreshed, isTrue);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () =>
              showOperationGrantSheet<void>(context, controller, (_) async {}),
          child: const Text('Open failure'));
    })));
    await tester.tap(find.text('Open failure'));
    await tester.pumpAndSettle();
    expect(find.textContaining('HEAD_CONFLICT'), findsOneWidget);
    expect(find.textContaining('Journey state changed'), findsOneWidget);
  });
}
