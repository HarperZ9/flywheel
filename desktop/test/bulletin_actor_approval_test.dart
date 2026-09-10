import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/models/approval_review_models.dart';
import 'support/bulletin_actor_approval.dart';
import 'support/bulletin_actor_exchange.dart';

const hash = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const proposalRef = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const grantRef = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const bulletinOrigin = 'http://127.0.0.1:54321';
const binding =
    GatewayJourneyBinding('jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', hash);
final op = GatewayOperation.exact(
    action: 'lane.call',
    clientRequestId: 'request-1',
    credentialRefs: [
      'cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ],
    operation: {
      'name': 'bulletin',
      'tool': 'board_write_post',
      'governance_tier': 'T2',
      'timeout': 20,
      'bulletin_base_url': bulletinOrigin,
      'args': {
        'room': 'findings',
        'parent_id': 'decoy-1',
        'body': '  {"task_id":"wrong","state":"reported"} 🌱\n'
      },
    });

class Records implements ActorRecords {
  String? corrupt;
  bool reject = false;
  final written = <String, Map<String, Object?>>{};
  final reads = <String>[];
  @override
  void write(String name, Map<String, Object?> value, int maxBytes) {
    written[name] = value;
  }

  @override
  Future<ActorRecord> wait(String name, int maxBytes, Duration timeout,
      {String? expectedSha}) async {
    reads.add(name);
    final decision = <String, Object?>{
      'schema_version': 1,
      'run_id': 'run-1',
      'slot_id': 'slot-1',
      'proposal_sha256': hash,
      'review_sha256': hash,
      'operation_sha256': hash,
      'proposal_ref': proposalRef,
      'reviewer_id': 'supervisor-1',
      'reviewer_type': 'assistant_supervisor',
      'decision': reject ? 'reject' : 'approve',
      'duration_ms': 12,
    };
    final value = name == 'decision.json'
        ? decision
        : <String, Object?>{
            'schema_version': 1,
            'run_id': 'run-1',
            'slot_id': 'slot-1',
            'reservation_id': 'reservation-1',
            'decision_sha256': actorDigest(utf8.encode(jsonEncode(decision))),
            'review_sha256': hash,
            'operation_sha256': hash,
          };
    if (corrupt == name) value['operation_sha256'] = 'b' * 64;
    return ActorRecord(utf8.encode(jsonEncode(value)));
  }
}

Map<String, Object?> review() => {
      'schema': 'flywheel.gateway-grant-review/v1',
      'proposal_ref': proposalRef,
      'planned_grant_ref': grantRef,
      'record_sha256': hash,
      'review_sha256': hash,
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'action': op.action,
      'journey_ref': binding.journeyRef,
      'expected_event_head': binding.eventHead,
      'client_request_id': op.clientRequestId,
      'destination': op.destination.toJson(),
      'tool': op.tool,
      'scopes': op.scopes,
      'data_refs': op.dataRefs,
      'credential_refs': op.credentialRefs,
      'execution_plan_sha256': hash,
      'operation_sha256': hash,
      'arguments_sha256': hash,
      'operation': op.operation,
      'expires_at': '2099-01-01T00:00:00Z',
    };

void main() {
  test('review fixture is admitted by production model', () {
    final value = GatewayGrantReview.fromJson(review());
    expect(value.invalidResponse, isFalse, reason: '${value.parseIssues}');
  });
  for (final failure in [
    'none',
    'capabilities',
    'review',
    'decision.json',
    'dispatch-permit.json',
    'grant',
    'expired',
    'invalid_expiry',
    'expiry_type',
    'recorder',
    'reject'
  ]) {
    test('reviewed production client path: $failure', () async {
      final records = Records()
        ..corrupt = failure
        ..reject = failure == 'reject';
      final paths = <String>[];
      final raw = MockClient((request) async {
        final path = request.url.path;
        paths.add(path);
        if (failure == 'recorder') {
          throw StateError('synthetic transport recorder failure');
        }
        var r = review();
        if (failure == 'review') {
          r['operation'] = {...op.operation, 'timeout': 19};
        }
        Object response;
        if (path.endsWith('/capabilities')) {
          response = {
            'schema': 'flywheel.gateway-grant-capabilities/v1',
            'reviewed_approval': failure != 'capabilities',
            'proposal_list': true,
            'proposal_read': true,
            'durable_reject': true,
            'review_max_bytes': 65536
          };
        } else if (path.endsWith('/prepare/lane.call')) {
          final fields = [
            'action',
            'journey_ref',
            'expected_event_head',
            'destination',
            'tool',
            'operation_sha256',
            'arguments_sha256',
            'scopes',
            'data_refs',
            'credential_refs',
            'expires_at'
          ];
          response = {
            'schema': 'flywheel.gateway-grant-proposal/v1',
            'proposal_ref': proposalRef,
            'planned_grant_ref': grantRef,
            'client_request_id': op.clientRequestId,
            for (final f in fields) f: r[f],
            'summary': {
              'schema': 'flywheel.gateway-grant-summary/v1',
              for (final f in fields) f: r[f],
              'effect': 'one dispatch after approval'
            }
          };
        } else if (path.endsWith('/read')) {
          response = {
            'schema': 'flywheel.gateway-grant-read/v1',
            'server_time': '2026-09-09T00:00:00Z',
            'proposal_state': 'prepared',
            'derived_state': 'pending',
            'record_sha256': hash,
            'review_available': true,
            'review': r
          };
        } else if (path.endsWith('/reject')) {
          response = {
            'schema': 'flywheel.gateway-grant-rejection/v1',
            'proposal_ref': proposalRef,
            'proposal_state': 'rejected',
            'record_sha256': hash
          };
        } else if (path.endsWith('/approve-reviewed-once')) {
          expect(records.reads, contains('dispatch-permit.json'));
          response = {
            'schema': 'flywheel.operation-grant-approval/v1',
            'grant_ref': failure == 'grant'
                ? 'gnt_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                : grantRef,
            'expires_at': {
                  'expired': '2000-01-01T00:00:00Z',
                  'invalid_expiry': '2099-99-99T00:00:00Z',
                  'expiry_type': 2099
                }[failure] ??
                '2099-01-01T00:00:00Z'
          };
        } else {
          expect(path, '/api/lane/bulletin/board_write_post');
          final dispatched = jsonDecode(request.body) as Map;
          expect(dispatched['args'], op.operation['args']);
          expect(dispatched['bulletin_base_url'], bulletinOrigin);
          response = {'status': 'posted_readback_match', 'post_id': 'reply-1'};
        }
        return http.Response(jsonEncode(response), 200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      });
      final driver = ActorApprovalDriver(
          GatewayGrantClient(GatewayClient(
              baseUrl: 'http://127.0.0.1:12345', httpClient: raw)),
          records,
          runId: 'run-1',
          slotId: 'slot-1',
          proposalSha: hash,
          recordingFailed: () => failure == 'recorder',
          reviewWait: const Duration(seconds: 1));
      await driver.run(op, binding);
      final result = records.written['result.json']!;
      expect(
          result['stage'],
          {
            'none': 'dispatch',
            'capabilities': 'capabilities',
            'review': 'review_binding',
            'decision.json': 'decision',
            'dispatch-permit.json': 'reservation',
            'grant': 'approve',
            'expired': 'approve',
            'invalid_expiry': 'approve',
            'expiry_type': 'approve',
            'recorder': 'capabilities',
            'reject': 'reject'
          }[failure]);
      expect(
          result['error_code'],
          failure == 'none' || failure == 'reject'
              ? null
              : failure == 'recorder'
                  ? 'native_recording_failed'
                  : 'native_driver_incomplete');
      if (failure == 'none') {
        await expectLater(
            driver.run(op, binding), throwsA(isA<ActorExchangeError>()));
      }
      expect(paths, isNot(contains('/api/gateway-grants/approve-once')));
      expect(paths.where((p) => p.endsWith('/board_write_post')).length,
          failure == 'none' ? 1 : 0,
          reason: 'stage=${result['stage']} paths=$paths');
      expect(
          result['disposition'],
          failure == 'none'
              ? 'response_received'
              : failure == 'reject'
                  ? 'rejected'
                  : 'incomplete');
    });
  }
}
