import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

Map<String, Object?> _proposalJson(String action) => {
      'schema': 'flywheel.grant-proposal/v1',
      'proposal_ref': _proposal,
      'planned_grant_ref': _grant,
      'action': action,
      'operation_sha256': _headA,
      'expires_at': '2026-08-15T12:00:00Z',
      if (action == 'check' || action == 'cancel') 'operation_ref': _operation,
    };

Map<String, Object?> _ackJson() => {
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': _journey,
      'event_head_sha256': _headB,
      'event_sha256': _headB,
      'projection_sha256': _headA,
      'idempotent_replay': false,
    };

Map<String, Object?> _projectionJson({String? lens = 'Verify'}) => {
      'schema': 'flywheel.evidence-journey-projection/v2',
      'journey_ref': _journey,
      'event_head_sha256': _headA,
      'fact_ids': const ['fact-1'],
      'claim_ids': const ['claim-1'],
      'checks': const [],
      'verdicts': const {'claim-1': 'UNDECIDED'},
      'missing_evidence': const [],
      'stage': 'running',
      'conclusion': null,
      'next_actions': const [],
      'detail': 'Server-owned detail',
      if (lens != null) 'lens': lens,
    };

Map<String, Object?> _exportJson() => {
      'schema': 'flywheel.evidence-journey-export/v2',
      'profile': 'flywheel.evidence-journey-custody/v2',
      'journey_ref': _journey,
      'source_event_head_sha256': _headA,
      'final_event_head_sha256': _headB,
      'final_projection_sha256': _headB,
      'packet_ref': 'packets/journey',
      'packet_digest': _headA,
      'structural_verdict': 'MATCH',
      'authenticity_verdict': 'UNVERIFIABLE',
      'rehash_resistance_verdict': 'MATCH',
      'idempotent_replay': false,
      'does_not_prove': const ['source completeness'],
    };

GatewayJourneyApi _api(Future<http.Response> Function(http.Request) handler) =>
    GatewayJourneyApi(GatewayClient(
        baseUrl: 'http://127.0.0.1:8799', httpClient: MockClient(handler)));

void main() {
  _grantRouteTests();
  _mutationRouteTests();
  _readAndTerminalRouteTests();
}

void _grantRouteTests() {
  test('grant preparation uses five fixed routes and exact public bodies',
      () async {
    final expected = <String, Map<String, dynamic>>{
      '/api/grants/prepare/create': {
        'goal': 'Preserve evidence',
        'intake_ref': 'intake.json',
        'client_request_id': 'create-1'
      },
      '/api/grants/prepare/append': {
        'journey_ref': _journey,
        'expected_event_head': _headA,
        'client_request_id': 'append-1',
        'command': {'type': 'advance_stage'}
      },
      '/api/grants/prepare/check': {
        'journey_ref': _journey,
        'expected_event_head': _headA,
        'client_request_id': 'check-1',
        'claim_id': 'claim-1',
        'oracle_id': 'code',
        'candidate_ref': 'candidate.py',
        'context_ref': 'context.json'
      },
      '/api/grants/prepare/cancel': {
        'journey_ref': _journey,
        'expected_event_head': _headA,
        'client_request_id': 'cancel-1',
        'operation_ref': _operation
      },
      '/api/grants/prepare/export': {
        'journey_ref': _journey,
        'expected_event_head': _headA,
        'client_request_id': 'export-1',
        'packet_ref': 'packets/journey'
      },
    };
    final seen = <String>[];
    final api = _api((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      seen.add(request.url.path);
      expect(body, expected[request.url.path]);
      return http.Response(
          jsonEncode(_proposalJson(request.url.pathSegments.last)), 200);
    });
    final intents = [
      GrantIntent.create(
          goal: 'Preserve evidence',
          intakeRef: 'intake.json',
          clientRequestId: 'create-1'),
      GrantIntent.append(
          journeyRef: _journey,
          expectedEventHead: _headA,
          clientRequestId: 'append-1',
          command: const {'type': 'advance_stage'}),
      GrantIntent.check(
          journeyRef: _journey,
          expectedEventHead: _headA,
          clientRequestId: 'check-1',
          claimId: 'claim-1',
          oracleId: 'code',
          candidateRef: 'candidate.py',
          contextRef: 'context.json'),
      GrantIntent.cancel(
          journeyRef: _journey,
          expectedEventHead: _headA,
          clientRequestId: 'cancel-1',
          operationRef: _operation),
      GrantIntent.export(
          journeyRef: _journey,
          expectedEventHead: _headA,
          clientRequestId: 'export-1',
          packetRef: 'packets/journey'),
    ];
    for (final intent in intents) {
      expect((await api.prepareGrant(intent)).invalidResponse, isFalse);
    }
    expect(seen, expected.keys);
  });
}

void _mutationRouteTests() {
  test('create append and check send canonical fields to fixed paths',
      () async {
    final seen = <(String, Map<String, dynamic>)>[];
    final api = _api((request) async {
      seen.add(
          (request.url.path, jsonDecode(request.body) as Map<String, dynamic>));
      return http.Response(jsonEncode(_ackJson()), 200);
    });
    await api.create(JourneyCreateRequest(
        goal: 'Preserve evidence',
        intakeRef: 'intake.json',
        clientRequestId: 'create-1',
        grantRef: _grant));
    await api.append(JourneyAppendRequest(
        journeyRef: _journey,
        expectedEventHead: _headA,
        clientRequestId: 'append-1',
        grantRef: _grant,
        command: const {'type': 'advance_stage'}));
    await api.check(JourneyCheckRequest(
        journeyRef: _journey,
        expectedEventHead: _headA,
        clientRequestId: 'check-1',
        grantRef: _grant,
        claimId: 'claim-1',
        oracleId: 'code',
        candidateRef: 'candidate.py',
        contextRef: 'context.json'));
    expect(seen.map((item) => item.$1), [
      '/api/journeys/create',
      '/api/journeys/append',
      '/api/journeys/check'
    ]);
    expect(seen[0].$2, {
      'goal': 'Preserve evidence',
      'intake_ref': 'intake.json',
      'client_request_id': 'create-1',
      'grant_ref': _grant
    });
    expect(seen[1].$2, {
      'journey_ref': _journey,
      'expected_event_head': _headA,
      'client_request_id': 'append-1',
      'grant_ref': _grant,
      'command': {'type': 'advance_stage'}
    });
    expect(seen[2].$2, {
      'journey_ref': _journey,
      'expected_event_head': _headA,
      'client_request_id': 'check-1',
      'grant_ref': _grant,
      'claim_id': 'claim-1',
      'oracle_id': 'code',
      'candidate_ref': 'candidate.py',
      'context_ref': 'context.json'
    });
  });
}

void _readAndTerminalRouteTests() {
  test('list and resume use fixed POST routes and typed projections', () async {
    final paths = <String>[];
    final api = _api((request) async {
      paths.add(request.url.path);
      final body = jsonDecode(request.body);
      if (request.url.path.endsWith('/list')) {
        expect(body, <String, dynamic>{});
        return http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-journey-list/v2',
              'journeys': [_projectionJson(lens: null)]
            }),
            200);
      }
      expect(body, {'journey_ref': 'jrn_value/with?query', 'lens': 'Verify'});
      return http.Response(jsonEncode(_projectionJson()), 200);
    });
    final listed = await api.list();
    final resumed =
        await api.resume('jrn_value/with?query', JourneyLens.verify);
    expect(paths, ['/api/journeys/list', '/api/journeys/resume']);
    expect(listed.single.journeyRef, _journey);
    expect(() => listed.clear(), throwsUnsupportedError);
    expect(resumed.lens, JourneyLens.verify);
  });

  test('cancel stays distinct and export sends exact fixed-route bodies',
      () async {
    final paths = <String>[];
    final api = _api((request) async {
      paths.add(request.url.path);
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      if (request.url.path.endsWith('/cancel')) {
        expect(body, {
          'journey_ref': _journey,
          'expected_event_head': _headA,
          'client_request_id': 'cancel-1',
          'grant_ref': _grant,
          'operation_ref': _operation
        });
        return http.Response(
            jsonEncode({
              'operation_ref': _operation,
              'state': 'cancelled',
              'event_head_sha256': _headB,
              'terminal_event_ref': _headA
            }),
            200);
      }
      expect(body, {
        'journey_ref': _journey,
        'expected_event_head': _headA,
        'client_request_id': 'export-1',
        'grant_ref': _grant,
        'packet_ref': 'packets/journey'
      });
      return http.Response(jsonEncode(_exportJson()), 200);
    });
    final cancelled = await api.cancel(JourneyCancelRequest(
        journeyRef: _journey,
        expectedEventHead: _headA,
        clientRequestId: 'cancel-1',
        grantRef: _grant,
        operationRef: _operation));
    final exported = await api.export(JourneyExportRequest(
        journeyRef: _journey,
        expectedEventHead: _headA,
        clientRequestId: 'export-1',
        grantRef: _grant,
        packetRef: 'packets/journey'));
    expect(paths, ['/api/journeys/cancel', '/api/journeys/export']);
    expect(cancelled.operationState, JourneyOperationState.cancelled);
    expect(exported.structuralVerdict, ReceiptState.match);
  });
}
