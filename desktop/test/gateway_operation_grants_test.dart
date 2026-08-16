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
const _binding = GatewayJourneyBinding(_journey, _head);
const _proposal = {
  'schema': 'flywheel.gateway-grant-proposal/v1',
  'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'action': 'plugin.probe',
  'journey_ref': _journey,
  'expected_event_head': _head,
  'client_request_id': 'request-1',
  'destination': {'kind': 'plugin', 'ref': 'gather'},
  'tool': 'plugin.probe',
  'operation_sha256': _head,
  'arguments_sha256': _head,
  'scopes': ['exec', 'network', 'plugin'],
  'data_refs': <String>[],
  'credential_refs': <String>[],
  'expires_at': '2026-08-15T12:02:00Z',
  'summary': {
    'schema': 'flywheel.gateway-grant-summary/v1',
    'action': 'plugin.probe',
    'journey_ref': _journey,
    'expected_event_head': _head,
    'destination': {'kind': 'plugin', 'ref': 'gather'},
    'tool': 'plugin.probe',
    'operation_sha256': _head,
    'arguments_sha256': _head,
    'scopes': ['exec', 'network', 'plugin'],
    'data_refs': <String>[],
    'credential_refs': <String>[],
    'effect': 'one dispatch after approval',
    'expires_at': '2026-08-15T12:02:00Z',
  }
};

GatewayOperation _probe() => GatewayOperation.pluginProbe(
    name: 'gather',
    clientRequestId: 'request-1',
    dataRefs: const [],
    credentialRefs: const []);

void main() {
  _modelTests();
  _clientRouteTest();
  _clientMismatchTest();
  _closeSheetTest();
  _denyApproveSheetTest();
  _bindingSheetTest();
}

void _modelTests() {
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

  test('operations reject malformed and duplicate authority references', () {
    for (final refs in <(List<String>, List<String>)>[
      (const ['not-a-data-ref'], const []),
      (const ['data_same', 'data_same'], const []),
      (
        const [],
        const [
          'cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        ]
      ),
    ]) {
      expect(
          () => GatewayOperation.pluginProbe(
              name: 'gather',
              clientRequestId: 'request-1',
              dataRefs: refs.$1,
              credentialRefs: refs.$2),
          throwsArgumentError);
    }
  });
}

void _clientRouteTest() {
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
    final operation = _probe();
    await client.prepare(operation, binding: _binding);
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
      'operation': {
        'name': 'gather',
        'data_refs': <String>[],
        'credential_refs': <String>[]
      }
    });
  });
}

void _clientMismatchTest() {
  test('grant client rejects structurally valid changed authority', () async {
    for (final changed in <String, Object?>{
      'destination': {'kind': 'plugin', 'ref': 'forum'},
      'scopes': ['exec', 'plugin'],
    }.entries) {
      final summary = Map<String, Object?>.from(
          _proposal['summary'] as Map<String, Object?>)
        ..[changed.key] = changed.value;
      final response = Map<String, Object?>.from(_proposal)
        ..[changed.key] = changed.value
        ..['summary'] = summary;
      final client = GatewayGrantClient(GatewayClient(
          baseUrl: 'https://gateway.invalid',
          httpClient: MockClient(
              (_) async => http.Response(jsonEncode(response), 200))));
      await expectLater(client.prepare(_probe(), binding: _binding),
          throwsA(isA<GatewayGrantException>()));
    }
  });
}

void _closeSheetTest() {
  testWidgets('closing the challenge consumes no approval and dispatches zero',
      (tester) async {
    var approvals = 0;
    var dispatches = 0;
    final controller =
        GatewayOperationController(GatewayGrantClient(GatewayClient(
            baseUrl: 'https://gateway.invalid',
            httpClient: MockClient((request) async {
              if (request.url.path.endsWith('approve-once')) approvals++;
              return http.Response(jsonEncode(_proposal), 200);
            }))));
    final operation = _probe();
    await controller.prepare(operation,
        binding: _binding,
        currentOperation: () => operation,
        currentBinding: () => _binding);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () => showOperationGrantSheet<int>(
              context, controller, (_) async => ++dispatches),
          child: const Text('Open close'));
    })));
    await tester.tap(find.text('Open close'));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(8, 8));
    await tester.pumpAndSettle();
    expect((approvals, dispatches), (0, 0));
  });
}

void _denyApproveSheetTest() {
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
    final operation = _probe();
    expect(
        await controller.prepare(operation,
            binding: _binding,
            currentOperation: () => operation,
            currentBinding: () => _binding),
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
            binding: _binding,
            currentOperation: () => operation,
            currentBinding: () => _binding),
        isTrue);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(dispatches, 1);
  });
}

void _bindingSheetTest() {
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
    final operation = _probe();
    var binding = _binding;
    await controller.prepare(operation,
        binding: _binding,
        currentOperation: () => operation,
        currentBinding: () => binding);
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return FilledButton(
          onPressed: () =>
              showOperationGrantSheet<int>(context, controller, (_) async => 1),
          child: const Text('Open stale'));
    })));
    await tester.tap(find.text('Open stale'));
    await tester.pumpAndSettle();
    binding = const GatewayJourneyBinding(_journey,
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(approvals, 0);
    expect(controller.proposal, isNull);
    expect(controller.failure?.code, 'OPERATION_CHANGED');
  });
}
