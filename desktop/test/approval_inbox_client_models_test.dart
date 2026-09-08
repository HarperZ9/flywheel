import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/client/approval_inbox_api.dart';
import 'package:flywheel_desktop/models/approval_inbox_models.dart';

const _hash =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _review =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  test('models parse capability gate, pagination, and exact review payload',
      () {
    final caps = GatewayGrantCapabilities.fromJson(const {
      'schema': 'flywheel.gateway-grant-capabilities/v1',
      'reviewed_approval': true,
      'proposal_list': true,
      'proposal_read': true,
      'durable_reject': true,
      'review_max_bytes': 32768,
    });
    expect(caps.ready, isTrue);
    expect(GatewayGrantCapabilities.fromJson(const {}).ready, isFalse);

    final list = GatewayGrantList.fromJson(_listBody(nextCursor: 'cursor-2'));
    expect(list.nextCursor, 'cursor-2');
    expect(list.indexComplete, isTrue);
    expect(list.listStatus, 'complete');
    expect(list.coverageScope, 'maintained_index');
    expect(list.recoveryRequired, '');
    expect(list.decidedRecentWindowSeconds, 86400);
    expect(list.inspectedIndexRows, 1);
    expect(list.recordReads, 1);
    expect(list.items.single.expiresAt, '2026-09-07T00:02:00Z');
    final incomplete = GatewayGrantList.fromJson(
        _listBody(indexComplete: false, listStatus: 'index_mutation_pending'));
    expect(incomplete.invalidResponse, isFalse);
    expect(incomplete.indexComplete, isFalse);
    expect(incomplete.listStatus, 'index_mutation_pending');
    final recovery = GatewayGrantList.fromJson(_listBody(
        indexComplete: false,
        listStatus: 'recovery_required',
        recoveryRequired: 'SCAN_LIMIT_EXCEEDED'));
    expect(recovery.invalidResponse, isFalse);
    expect(recovery.coverageScope, 'maintained_index');
    expect(recovery.recoveryRequired, 'SCAN_LIMIT_EXCEEDED');

    final read = GatewayGrantRead.fromJson(_readBody());
    expect(read.approvable, isTrue);
    expect(read.review!.operation['nested'], {'flag': true});
    expect(read.review!.reviewSha256, _review);
  });

  test(
      'grant inbox client uses reviewed routes, cursor, and never legacy approve',
      () async {
    final calls = <http.Request>[];
    final client = GatewayGrantClient(GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        calls.add(request);
        final path = request.url.path;
        final body = switch (path) {
          '/api/gateway-grants/capabilities' => _capabilitiesBody(),
          '/api/gateway-grants/list' => _listBody(nextCursor: 'cursor-2'),
          '/api/gateway-grants/read' => _readBody(),
          '/api/gateway-grants/approve-reviewed-once' => {
              'schema': 'flywheel.operation-grant-approval/v1',
              'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              'expires_at': '2026-09-07T00:02:00Z',
            },
          '/api/gateway-grants/reject' => {
              'schema': 'flywheel.gateway-grant-rejection/v1',
              'proposal_ref': _proposal,
              'proposal_state': 'rejected',
              'record_sha256': _hash,
            },
          _ => throw StateError('unexpected $path'),
        };
        return http.Response(jsonEncode(body), 200);
      }),
    ));

    expect((await client.capabilities()).ready, isTrue);
    expect(
        (await client.listPending(cursor: 'cursor-1')).nextCursor, 'cursor-2');
    expect((await client.readProposal(_proposal)).review!.tool, 'plugin.probe');
    await client.approveReviewed(_proposal, _review);
    await client.rejectProposal(_proposal, _hash);

    expect(calls.map((c) => c.url.path), [
      '/api/gateway-grants/capabilities',
      '/api/gateway-grants/list',
      '/api/gateway-grants/read',
      '/api/gateway-grants/approve-reviewed-once',
      '/api/gateway-grants/reject',
    ]);
    final listBody = jsonDecode(calls[1].body) as Map<String, dynamic>;
    expect(listBody['cursor'], 'cursor-1');
    final approveBody = jsonDecode(calls[3].body) as Map<String, dynamic>;
    expect(approveBody, {
      'schema': 'flywheel.gateway-grant-reviewed-approval-request/v1',
      'proposal_ref': _proposal,
      'review_sha256': _review,
    });
    final rejectBody = jsonDecode(calls[4].body) as Map<String, dynamic>;
    expect(rejectBody, {
      'schema': 'flywheel.gateway-grant-reject-request/v1',
      'proposal_ref': _proposal,
      'expected_record_sha256': _hash,
    });
  });

  test('relay run parsing separates active terminal unknown and unavailable',
      () async {
    final api = GatewayApprovalInboxApi(GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/relay/runs') {
          return http.Response(
              jsonEncode({
                'schema': 'flywheel.agent-runs/v1',
                'runs': [
                  {'run_id': 'run-active-1', 'status': 'running'},
                  {'run_id': 'run-done-1', 'status': 'completed'},
                  {'run_id': 'run-failed-1', 'status': 'failed'},
                  {'run_id': 'run-weird-1', 'status': 'paused'},
                ],
              }),
              200);
        }
        throw StateError('unexpected ${request.url.path}');
      }),
    ));

    final snapshot = await api.activeWorkSnapshot();
    expect(snapshot.unavailable, isFalse);
    expect(snapshot.active.map((item) => item.runId), ['run-active-1']);
    expect(snapshot.terminal.map((item) => item.runId),
        ['run-done-1', 'run-failed-1']);
    expect(snapshot.unknown.map((item) => item.runId), ['run-weird-1']);

    final failingApi = GatewayApprovalInboxApi(GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((_) async => http.Response('nope', 500)),
    ));
    final unavailable = await failingApi.activeWorkSnapshot();
    expect(unavailable.unavailable, isTrue);
    expect(unavailable.active, isEmpty);
  });
}

Map<String, Object?> _capabilitiesBody() => const {
      'schema': 'flywheel.gateway-grant-capabilities/v1',
      'reviewed_approval': true,
      'proposal_list': true,
      'proposal_read': true,
      'durable_reject': true,
      'review_max_bytes': 32768,
    };

Map<String, Object?> _listBody({
  String? nextCursor,
  bool indexComplete = true,
  String listStatus = 'complete',
  String coverageScope = 'maintained_index',
  String? recoveryRequired,
}) =>
    {
      'schema': 'flywheel.gateway-grant-list/v1',
      'server_time': '2026-09-07T00:00:00Z',
      'state': 'pending',
      'items': [
        {
          'schema': 'flywheel.gateway-grant-list-item/v1',
          'proposal_ref': _proposal,
          'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'proposal_state': 'prepared',
          'derived_state': 'pending',
          'record_sha256': _hash,
          'expires_at': '2026-09-07T00:02:00Z',
          'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'review_available': true,
          'review_sha256': _review,
          'summary': {'schema': 'flywheel.gateway-grant-summary/v1'},
        }
      ],
      'next_cursor': nextCursor,
      'index_complete': indexComplete,
      'list_status': listStatus,
      'coverage_scope': coverageScope,
      'recovery_required': recoveryRequired,
      'decided_recent_window_seconds': 86400,
      'inspected_index_rows': 1,
      'record_reads': 1,
    };

Map<String, Object?> _readBody() => {
      'schema': 'flywheel.gateway-grant-read/v1',
      'server_time': '2026-09-07T00:00:00Z',
      'proposal_state': 'prepared',
      'derived_state': 'pending',
      'record_sha256': _hash,
      'review_available': true,
      'review': {
        'schema': 'flywheel.gateway-grant-review/v1',
        'proposal_ref': _proposal,
        'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'record_sha256': _hash,
        'review_sha256': _review,
        'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'action': 'plugin.probe',
        'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'expected_event_head': _hash,
        'client_request_id': 'request-1',
        'destination': {'kind': 'plugin', 'ref': 'gather'},
        'tool': 'plugin.probe',
        'scopes': ['exec', 'network', 'plugin'],
        'data_refs': <String>[],
        'credential_refs': ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        'execution_plan_sha256': _hash,
        'operation_sha256': _hash,
        'arguments_sha256': _hash,
        'operation': {
          'name': 'gather',
          'nested': {'flag': true},
          'credential_refs': ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        },
        'expires_at': '2026-09-07T00:02:00Z',
      },
    };
