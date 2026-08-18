import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _headA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _headB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _checkA = <String, Object?>{
  'check_id': 'check-1',
  'claim_id': 'claim-1',
  'verdict': 'FAIL',
  'receipt_refs': ['receipts/check-1.json'],
  'receipt_state': 'MATCH',
  'numerator': 0,
  'denominator': 1,
  'does_not_prove': 'claim correctness',
};
const _missingA = <String, Object?>{
  'kind': 'fact',
  'id': 'fact-1',
  'receipt_refs': ['receipts/pending'],
};

Map<String, Object?> _fixture({
  required String lens,
  String head = _headA,
  List<Object?> factIds = const ['fact-1'],
  List<Object?> claimIds = const ['claim-1'],
  List<Object?> checks = const [_checkA],
  Map<String, Object?> verdicts = const {'claim-1': 'FAIL'},
  List<Object?> missingEvidence = const [_missingA],
  String stage = 'running',
  Object? conclusion,
  String detail = 'lens detail',
  List<Object?> nextActions = const <Object?>[],
}) =>
    {
      'schema': 'flywheel.evidence-journey-projection/v2',
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'event_head_sha256': head,
      'fact_ids': factIds,
      'claim_ids': claimIds,
      'checks': checks,
      'verdicts': verdicts,
      'missing_evidence': missingEvidence,
      'stage': stage,
      'conclusion': conclusion,
      'next_actions': nextActions,
      'detail': detail,
      'lens': lens,
      'presentation': {lens.toLowerCase(): detail},
    };

void main() {
  _lensIdentityTests();
  _coreIdentityTests();
  _summaryAndListTests();
  _responseParsingTests();
  _publicTextTests();
  _cancelTests();
}

void _lensIdentityTests() {
  test('Rescue Diagnose and Verify retain identical evidence identity', () {
    final rescue = JourneyProjection.fromJson(_fixture(
      lens: 'Rescue',
      detail: 'next action first',
      nextActions: const [
        {
          'action_id': 'inspect-1',
          'kind': 'inspect',
          'description': 'Inspect',
          'basis_refs': ['claim-1'],
        },
      ],
    ));
    final diagnose = JourneyProjection.fromJson(_fixture(
      lens: 'Diagnose',
      detail: 'missing evidence first',
    ));
    final verify = JourneyProjection.fromJson(_fixture(
      lens: 'Verify',
      detail: 'checks first',
    ));

    expect(
        [rescue, diagnose, verify]
            .every((projection) => !projection.invalidResponse),
        isTrue);
    expect(rescue.sameEvidenceAs(diagnose), isTrue);
    expect(diagnose.sameEvidenceAs(verify), isTrue);
    expect(verify.sameEvidenceAs(rescue), isTrue);
    expect({rescue.lens, diagnose.lens, verify.lens},
        {JourneyLens.rescue, JourneyLens.diagnose, JourneyLens.verify});
  });
}

void _coreIdentityTests() {
  test('sameEvidenceAs rejects a change to every server-owned core field', () {
    final source = JourneyProjection.fromJson(_fixture(lens: 'Rescue'));
    final changed = <JourneyProjection>[
      JourneyProjection.fromJson(_fixture(lens: 'Verify', head: _headB)),
      JourneyProjection.fromJson(
          _fixture(lens: 'Verify', factIds: const ['fact-2'])),
      JourneyProjection.fromJson(
          _fixture(lens: 'Verify', claimIds: const ['claim-2'])),
      JourneyProjection.fromJson(_fixture(lens: 'Verify', checks: const [
        {
          'check_id': 'check-1',
          'claim_id': 'claim-1',
          'verdict': 'FAIL',
          'receipt_refs': ['receipts/check-1.json'],
          'receipt_state': 'MATCH',
          'numerator': 1,
          'denominator': 1,
          'does_not_prove': 'claim correctness',
        },
      ])),
      JourneyProjection.fromJson(
          _fixture(lens: 'Verify', verdicts: const {'claim-1': 'UNDECIDED'})),
      JourneyProjection.fromJson(
          _fixture(lens: 'Verify', missingEvidence: const [
        {
          'kind': 'fact',
          'id': 'fact-2',
          'receipt_refs': ['receipts/pending'],
        },
      ])),
      JourneyProjection.fromJson(_fixture(lens: 'Verify', stage: 'concluded')),
      JourneyProjection.fromJson(_fixture(lens: 'Verify', conclusion: const {
        'summary': 'Bounded',
        'does_not_prove': 'claim correctness',
      })),
    ];

    expect(changed, hasLength(8));
    for (final projection in changed) {
      expect(source.sameEvidenceAs(projection), isFalse);
    }
  });
}

void _summaryAndListTests() {
  test('summary parses list projection without changing its core identity', () {
    final json = _fixture(lens: 'Verify');
    final projection = JourneyProjection.fromJson(json);
    final summary = JourneySummary.fromJson(json);

    expect(summary.invalidResponse, isFalse);
    expect(summary.journeyRef, projection.journeyRef);
    expect(summary.eventHeadSha256, projection.eventHeadSha256);
    expect(summary.stage, projection.stage);
    expect(summary.sameEvidenceAs(projection), isTrue);
  });

  test('list envelope validates schema and owns immutable summaries', () {
    final durable = _fixture(lens: 'Verify')
      ..remove('lens')
      ..remove('detail')
      ..remove('presentation');
    final sourceItems = <Object?>[durable];
    final result = JourneyListResult.fromJson({
      'schema': 'flywheel.evidence-journey-list/v2',
      'journeys': sourceItems,
    });
    sourceItems.clear();

    expect(result.invalidResponse, isFalse);
    expect(result.journeys, hasLength(1));
    expect(result.journeys.single.stage, JourneyStage.running);
    expect(() => result.journeys.clear(), throwsUnsupportedError);

    for (final journeys in [
      null,
      'not-a-list',
      const [1]
    ]) {
      final malformed = JourneyListResult.fromJson({
        'schema': 'flywheel.evidence-journey-list/v2',
        if (journeys != null) 'journeys': journeys,
      });
      expect(malformed.journeys, isEmpty, reason: '$journeys');
      expect(malformed.invalidResponse, isTrue, reason: '$journeys');
      expect(malformed.parseIssues.map((issue) => issue.field),
          contains('journeys'));
    }
  });
}

void _responseParsingTests() {
  test('grant acknowledgement export and public failure parse exactly', () {
    final proposal = GrantProposal.fromJson(const {
      'schema': 'flywheel.grant-proposal/v1',
      'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'action': 'check',
      'operation_sha256': _headA,
      'expires_at': '2026-08-15T12:02:00Z',
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    });
    final grant = GrantRef.fromJson(const {
      'schema': 'flywheel.operation-grant-approval/v1',
      'grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'expires_at': '2026-08-15T12:02:00Z',
    });
    final ack = JourneyMutationAck.fromJson(const {
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'event_head_sha256': _headA,
      'event_sha256': _headA,
      'projection_sha256': _headB,
      'idempotent_replay': false,
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'state': 'running',
    });
    final exported = JourneyExportResult.fromJson(const {
      'schema': 'flywheel.evidence-journey-export/v2',
      'profile': 'flywheel.evidence-journey-custody/v2',
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'source_event_head_sha256': _headA,
      'final_event_head_sha256': _headB,
      'final_projection_sha256': _headA,
      'packet_ref': 'packets/journey',
      'packet_digest': _headB,
      'structural_verdict': 'MATCH',
      'authenticity_verdict': 'UNVERIFIABLE',
      'rehash_resistance_verdict': 'MATCH',
      'idempotent_replay': false,
      'does_not_prove': ['claim correctness'],
    });
    final failure = JourneyFailure.fromJson(const {
      'schema': 'flywheel.evidence-transport-error/v1',
      'error': {'code': 'HEAD_CONFLICT', 'message': 'Journey state changed'},
    });

    expect(proposal.operationRef, 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(grant.grantRef, proposal.plannedGrantRef);
    expect(ack.operationState, JourneyOperationState.running);
    expect(exported.structuralVerdict, ReceiptState.match);
    expect(exported.authenticityVerdict, ReceiptState.unverifiable);
    expect(failure.code, 'HEAD_CONFLICT');
    expect(failure.detail, 'Journey state changed');
    expect(
        [proposal, grant, ack, exported, failure]
            .every((model) => !model.invalidResponse),
        isTrue);
  });
}

void _publicTextTests() {
  test('unsafe failure detail is not retained for display', () {
    const unsafeDetails = [
      r'C:\private\credential-token.txt',
      'error FiLe:private/input.json',
      'at (/etc/passwd)',
      'path={/Users/private/input.json}',
      'provider ghp_abcdefghijklmnopqrstuvwxyz123456',
      'provider sk-liveabcdefghijklmnop',
      'slack xoxb-abcdefghijklmnop',
      '-----BEGIN PRIVATE KEY-----',
      'password=abcdefghijklmnop',
      'api_key=abcdefghijklmnop',
    ];
    for (final detail in unsafeDetails) {
      final failure = JourneyFailure.fromJson({
        'schema': 'flywheel.evidence-transport-error/v1',
        'error': {'code': 'STORE_COMMIT_FAILED', 'message': detail},
      });
      expect(failure.detail, 'Response detail unavailable', reason: detail);
      expect(failure.invalidResponse, isTrue, reason: detail);
      expect(failure.parseIssues.single.rawValue, '[redacted]', reason: detail);
    }
  });
}

void _cancelTests() {
  test('cancel parses its distinct live response without synthetic ack fields',
      () {
    final cancelled = JourneyCancelResult.fromJson(const {
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'state': 'cancelled',
      'event_head_sha256': _headA,
      'terminal_event_ref': _headB,
    });
    final unknown = JourneyCancelResult.fromJson(const {
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'state': 'paused',
      'event_head_sha256': _headA,
      'terminal_event_ref': _headB,
    });

    expect(cancelled.invalidResponse, isFalse);
    expect(cancelled.operationState, JourneyOperationState.cancelled);
    expect(cancelled.terminalEventRef, _headB);
    expect(unknown.operationState, JourneyOperationState.invalidResponse);
    expect(unknown.rawOperationState, 'paused');
    expect(unknown.invalidResponse, isTrue);
  });
}
