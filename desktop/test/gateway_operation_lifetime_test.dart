import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding(_journey, _head);

Map<String, Object?> _proposal(GatewayOperation operation) => {
      'schema': 'flywheel.gateway-grant-proposal/v1',
      'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'action': operation.action,
      'journey_ref': _journey,
      'expected_event_head': _head,
      'client_request_id': operation.clientRequestId,
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
        'action': operation.action,
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
const _approval = {
  'schema': 'flywheel.operation-grant-approval/v1',
  'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'expires_at': '2026-08-15T12:02:00Z'
};

GatewayOperation _probe(String name) => GatewayOperation.pluginProbe(
    name: name,
    clientRequestId: 'request-1',
    dataRefs: const [],
    credentialRefs: const []);

GatewayOperation _exact({
  String action = 'plugin.call',
  GatewayDestination destination = const GatewayDestination('plugin', 'gather'),
  String tool = 'find',
  List<String> dataRefs = const ['data_a'],
  List<String> credentialRefs = const ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
  String request = 'request-1',
  String value = 'same',
}) =>
    GatewayOperation.exact(
        action: action,
        operation: {
          'name': 'gather',
          'tool': 'find',
          'arguments': {'v': value}
        },
        destination: destination,
        tool: tool,
        dataRefs: dataRefs,
        credentialRefs: credentialRefs,
        clientRequestId: request);

GatewayOperationController _controller(MockClient transport) =>
    GatewayOperationController(GatewayGrantClient(GatewayClient(
        baseUrl: 'https://gateway.invalid', httpClient: transport)));

void main() {
  _operationEqualityTest();
  _overlappingPrepareTest();
  _editBeforeApprovalTest();
  _editDuringApprovalTest();
  _preDispatchRecheckTest();
  _doubleApprovalTest();
  _invalidationGuardTest();
  _headConflictRefreshTest();
}

void _operationEqualityTest() {
  test('operation equality includes every authority-bearing field', () {
    final operation = _exact();
    expect(operation, _exact());
    for (final changed in <GatewayOperation>[
      _exact(action: 'plugin.probe'),
      _exact(destination: const GatewayDestination('plugin', 'forum')),
      _exact(tool: 'search'),
      _exact(dataRefs: const ['data_b']),
      _exact(credentialRefs: const ['cred_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb']),
      _exact(request: 'request-2'),
      _exact(value: 'changed'),
    ]) {
      expect(operation == changed, isFalse);
    }
  });
}

void _overlappingPrepareTest() {
  test('overlapping prepare is refused while the first request is unsettled',
      () async {
    final response = Completer<http.Response>();
    var calls = 0;
    final operation = _probe('gather');
    final controller = _controller(MockClient((_) {
      calls++;
      return response.future;
    }));
    final first = controller.prepare(operation,
        binding: _binding,
        currentOperation: () => operation,
        currentBinding: () => _binding);
    await Future<void>.delayed(Duration.zero);
    expect(
        await controller.prepare(operation,
            binding: _binding,
            currentOperation: () => operation,
            currentBinding: () => _binding),
        isFalse);
    response.complete(http.Response(jsonEncode(_proposal(operation)), 200));
    expect(await first, isTrue);
    expect(calls, 1);
  });
}

void _editBeforeApprovalTest() {
  test('operation edit after prepare prevents approval and dispatch', () async {
    var approvals = 0;
    var dispatches = 0;
    var current = _probe('gather');
    final captured = current;
    final controller = _controller(MockClient((request) async {
      if (request.url.path.endsWith('approve-once')) approvals++;
      return http.Response(jsonEncode(_proposal(captured)), 200);
    }));
    expect(
        await controller.prepare(captured,
            binding: _binding,
            currentOperation: () => current,
            currentBinding: () => _binding),
        isTrue);
    current = _probe('forum');
    final result = await controller.approveAndDispatch((_) async {
      dispatches++;
      return true;
    });
    expect(result, isNull);
    expect(approvals, 0);
    expect(dispatches, 0);
    expect(controller.failure?.code, 'OPERATION_CHANGED');
  });
}

void _editDuringApprovalTest() {
  test('operation edit while approval is pending prevents dispatch', () async {
    final approval = Completer<http.Response>();
    var dispatches = 0;
    var current = _probe('gather');
    final captured = current;
    final controller = _controller(MockClient((request) async {
      if (request.url.path.endsWith('approve-once')) return approval.future;
      return http.Response(jsonEncode(_proposal(captured)), 200);
    }));
    expect(
        await controller.prepare(captured,
            binding: _binding,
            currentOperation: () => current,
            currentBinding: () => _binding),
        isTrue);
    final result = controller.approveAndDispatch((_) async => ++dispatches);
    await Future<void>.delayed(Duration.zero);
    current = _probe('forum');
    approval.complete(http.Response(jsonEncode(_approval), 200));
    expect(await result, isNull);
    expect(dispatches, 0);
    expect(controller.failure?.code, 'OPERATION_CHANGED');
  });
}

void _preDispatchRecheckTest() {
  test('operation is rechecked again immediately before dispatch', () async {
    var reads = 0;
    var dispatches = 0;
    final operation = _probe('gather');
    final controller = _controller(MockClient((request) async => http.Response(
        jsonEncode(request.url.path.endsWith('approve-once')
            ? _approval
            : _proposal(operation)),
        200)));
    await controller.prepare(operation,
        binding: _binding,
        currentOperation: () => ++reads == 4 ? _probe('forum') : operation,
        currentBinding: () => _binding);
    final result = await controller.approveAndDispatch((_) async {
      dispatches++;
      return true;
    });
    expect(result, isNull);
    expect(dispatches, 0);
    expect(controller.failure?.code, 'OPERATION_CHANGED');
  });
}

void _doubleApprovalTest() {
  test('double approval activation issues one approval and dispatch', () async {
    final approval = Completer<http.Response>();
    var approvals = 0;
    var dispatches = 0;
    final operation = _probe('gather');
    final controller = _controller(MockClient((request) async {
      if (!request.url.path.endsWith('approve-once')) {
        return http.Response(jsonEncode(_proposal(operation)), 200);
      }
      approvals++;
      return approval.future;
    }));
    await controller.prepare(operation,
        binding: _binding,
        currentOperation: () => operation,
        currentBinding: () => _binding);
    final first = controller.approveAndDispatch((_) async => ++dispatches);
    await Future<void>.delayed(Duration.zero);
    expect(
        await controller.approveAndDispatch((_) async => ++dispatches), isNull);
    approval.complete(http.Response(jsonEncode(_approval), 200));
    expect(await first, 1);
    expect((approvals, dispatches), (1, 1));
  });
}

void _invalidationGuardTest() {
  test('invalidation cannot release an unsettled lifetime guard', () async {
    final response = Completer<http.Response>();
    final operation = _probe('gather');
    final controller = _controller(MockClient((_) => response.future));
    final first = controller.prepare(operation,
        binding: _binding,
        currentOperation: () => operation,
        currentBinding: () => _binding);
    await Future<void>.delayed(Duration.zero);
    controller.invalidate();
    expect(controller.pending, isTrue);
    expect(
        await controller.prepare(operation,
            binding: _binding,
            currentOperation: () => operation,
            currentBinding: () => _binding),
        isFalse);
    response.complete(http.Response(jsonEncode(_proposal(operation)), 200));
    expect(await first, isFalse);
    expect(controller.pending, isFalse);
    expect(controller.failure, isNull);
    expect(controller.proposal, isNull);
  });
}

void _headConflictRefreshTest() {
  test('head conflict refreshes before typed failure is published', () async {
    final order = <String>[];
    final controller = _controller(MockClient((_) async => http.Response(
        jsonEncode({
          'schema': 'flywheel.evidence-transport-error/v1',
          'error': {'code': 'HEAD_CONFLICT', 'message': 'fixed'}
        }),
        409)));
    controller.addListener(() {
      if (controller.failure != null) order.add('failure');
    });
    final operation = _probe('gather');
    expect(
        await controller.prepare(operation,
            binding: _binding,
            currentOperation: () => operation,
            currentBinding: () => _binding,
            refreshOnHeadConflict: () async => order.add('refresh')),
        isFalse);
    expect(order, ['refresh', 'failure']);
    expect(controller.failure?.code, 'HEAD_CONFLICT');
  });
}
