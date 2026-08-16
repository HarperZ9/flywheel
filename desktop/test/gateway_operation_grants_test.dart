import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = {
  'schema': 'flywheel.gateway-grant-proposal/v1',
  'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'action': 'plugin.probe',
  'journey_ref': _journey,
  'expected_event_head': _head,
  'client_request_id': 'request-1',
  'tool': 'plugin.probe',
  'operation_sha256': _head,
  'arguments_sha256': _head,
  'scopes': ['exec', 'network', 'plugin'],
  'data_refs': <String>[],
  'credential_refs': <String>[],
  'expires_at': '2026-08-15T12:02:00Z',
  'summary': {
    'operation': 'plugin.probe',
    'journey_ref': _journey,
    'expected_event_head': _head,
    'tool': 'plugin.probe',
    'arguments_sha256': _head,
    'scopes': ['exec', 'network', 'plugin'],
    'data_refs': <String>[],
    'credential_refs': <String>[],
    'effect': 'one dispatch after approval',
    'expires_at': '2026-08-15T12:02:00Z',
  }
};

void main() {
  _modelAndClientTests();
  _sheetTests();
}

void _modelAndClientTests() {
  test('models reject wrong schemas prefixes and extra fields', () {
    expect(GatewayGrantProposal.fromJson(_proposal).invalidResponse, isFalse);
    for (final changed in [
      {..._proposal, 'schema': 'flywheel.grant-proposal/v1'},
      {..._proposal, 'proposal_ref': 'bad'},
      {..._proposal, 'extra': 'field'},
    ]) {
      expect(GatewayGrantProposal.fromJson(changed).invalidResponse, isTrue);
    }
  });

  test('grant client emits exact prepare and approve routes', () async {
    final calls = <http.Request>[];
    final transport = MockClient((request) async {
      calls.add(request);
      final body = request.url.path.endsWith('approve-once')
          ? {
              'schema': 'flywheel.operation-grant-approval/v1',
              'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              'expires_at': '2026-08-15T12:02:00Z'
            }
          : _proposal;
      return http.Response(jsonEncode(body), 200);
    });
    final client = GatewayGrantClient(GatewayClient(
        baseUrl: 'https://gateway.invalid', httpClient: transport));
    final operation = GatewayOperation.pluginProbe(
        name: 'gather', clientRequestId: 'request-1');
    await client.prepare(operation, journeyRef: _journey, eventHead: _head);
    await client.approve('prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(calls.map((call) => call.url.path), [
      '/api/gateway-grants/prepare/plugin.probe',
      '/api/gateway-grants/approve-once'
    ]);
    expect(jsonDecode(calls.first.body), {
      'schema': 'flywheel.gateway-operation/v1',
      'journey_ref': _journey,
      'expected_event_head': _head,
      'client_request_id': 'request-1',
      'operation': {'name': 'gather'}
    });
  });
}

void _sheetTests() {
  testWidgets('sheet deny dispatches nothing and approve dispatches once',
      (tester) async {
    var dispatches = 0;
    final transport = MockClient((request) async => http.Response(
        jsonEncode(request.url.path.endsWith('approve-once')
            ? {
                'schema': 'flywheel.operation-grant-approval/v1',
                'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'expires_at': '2026-08-15T12:02:00Z'
              }
            : _proposal),
        200));
    final controller = GatewayOperationController(GatewayGrantClient(
        GatewayClient(
            baseUrl: 'https://gateway.invalid', httpClient: transport)));
    final operation = GatewayOperation.pluginProbe(
        name: 'gather', clientRequestId: 'request-1');
    expect(
        await controller.prepare(operation,
            journeyRef: _journey, eventHead: _head),
        isTrue);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () => showOperationGrantSheet<int>(
              context, controller, (_) async => ++dispatches),
          child: const Text('Open'));
    })));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.text('exec'), findsOneWidget);
    await tester.tap(find.text('Deny'));
    await tester.pumpAndSettle();
    expect(dispatches, 0);
    expect(
        await controller.prepare(operation,
            journeyRef: _journey, eventHead: _head),
        isTrue);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(dispatches, 1);
  });

  testWidgets('changed Journey binding invalidates before approval',
      (tester) async {
    var approvals = 0;
    final transport = MockClient((request) async {
      if (request.url.path.endsWith('approve-once')) approvals++;
      return http.Response(jsonEncode(_proposal), 200);
    });
    final controller = GatewayOperationController(GatewayGrantClient(
        GatewayClient(
            baseUrl: 'https://gateway.invalid', httpClient: transport)));
    final operation = GatewayOperation.pluginProbe(
        name: 'gather', clientRequestId: 'request-1');
    await controller.prepare(operation, journeyRef: _journey, eventHead: _head);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () => showOperationGrantSheet<int>(
              context, controller, (_) async => 1,
              stillCurrent: (_) => false),
          child: const Text('Open stale'));
    })));
    await tester.tap(find.text('Open stale'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(approvals, 0);
    expect(controller.proposal, isNull);
  });
}
