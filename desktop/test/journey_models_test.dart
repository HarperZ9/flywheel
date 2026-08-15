import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _projectionSha =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, Object?> _projection({
  Object? factIds = const ['fact-1'],
  Object? claimIds = const ['claim-1'],
  Object? checks = const <Object?>[],
  Object? missingEvidence = const <Object?>[],
  Object? nextActions = const <Object?>[],
  Object? verdicts = const {'claim-1': 'UNDECIDED'},
  Object? stage = 'running',
  Object? lens = 'Rescue',
  Object? schema = 'flywheel.evidence-journey-projection/v2',
}) =>
    {
      'schema': schema,
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'event_head_sha256': _head,
      'fact_ids': factIds,
      'claim_ids': claimIds,
      'checks': checks,
      'verdicts': verdicts,
      'missing_evidence': missingEvidence,
      'stage': stage,
      'conclusion': null,
      'next_actions': nextActions,
      'detail': 'Server-owned diagnostic',
      'lens': lens,
      'presentation': const {'next_actions': <Object?>[]},
    };

void main() {
  test('projection parses exact server-owned states and core fields', () {
    final projection = JourneyProjection.fromJson(_projection(
      checks: const [
        {
          'check_id': 'check-1',
          'claim_id': 'claim-1',
          'verdict': 'UNVERIFIABLE',
          'receipt_refs': ['receipts/check-1.json'],
          'receipt_state': 'present_unchecked',
          'numerator': 0,
          'denominator': 1,
          'does_not_prove': 'claim correctness',
        },
      ],
      missingEvidence: const [
        {
          'kind': 'claim',
          'id': 'claim-1',
          'receipt_refs': ['receipts/pending'],
        },
      ],
      nextActions: const [
        {
          'action_id': 'inspect-1',
          'kind': 'inspect',
          'description': 'Inspect the receipt',
          'basis_refs': ['claim-1'],
        },
      ],
    ));

    expect(projection.invalidResponse, isFalse);
    expect(projection.journeyRef, 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(projection.eventHeadSha256, _head);
    expect(projection.factIds, ['fact-1']);
    expect(projection.claimIds, ['claim-1']);
    expect(projection.stage, JourneyStage.running);
    expect(projection.lens, JourneyLens.rescue);
    expect(projection.verdicts['claim-1'], EvidenceVerdict.undecided);
    expect(
        projection.checks.single.receiptState, ReceiptState.presentUnchecked);
    expect(projection.checks.single.receiptRefs, ['receipts/check-1.json']);
    expect(projection.missingEvidence.single.id, 'claim-1');
    expect(projection.nextActions.single.kind, 'inspect');
    expect(projection.detail, 'Server-owned diagnostic');
  });

  test('all exact receipt wire values parse without promotion', () {
    const values = {
      'missing': ReceiptState.missing,
      'present_unchecked': ReceiptState.presentUnchecked,
      'MATCH': ReceiptState.match,
      'DRIFT': ReceiptState.drift,
      'TAMPERED': ReceiptState.tampered,
      'UNVERIFIABLE': ReceiptState.unverifiable,
    };
    for (final entry in values.entries) {
      final check = JourneyCheck.fromJson({
        'check_id': 'check-${entry.key}',
        'claim_id': 'claim-1',
        'verdict': 'UNVERIFIABLE',
        'receipt_refs': ['receipts/value.json'],
        'receipt_state': entry.key,
        'numerator': 0,
        'denominator': 1,
        'does_not_prove': 'truth',
      }, 'checks[0]');
      expect(check.receiptState, entry.value, reason: entry.key);
      expect(check.rawReceiptState, entry.key);
      expect(check.parseIssues, isEmpty);
    }
  });

  test('unknown controlled values stay raw and become invalid response', () {
    final projection = JourneyProjection.fromJson(_projection(
      schema: 'flywheel.evidence-journey-projection/v9',
      stage: 'archived',
      lens: 'rescue',
      verdicts: const {'claim-1': 'MAYBE'},
      checks: const [
        {
          'check_id': 'check-1',
          'claim_id': 'claim-1',
          'verdict': 'CERTAIN',
          'receipt_refs': ['receipts/check-1.json'],
          'receipt_state': 'SIGNED',
          'numerator': 1,
          'denominator': 1,
          'does_not_prove': 'truth',
        },
      ],
    ));

    expect(projection.invalidResponse, isTrue);
    expect(projection.stage, JourneyStage.invalidResponse);
    expect(projection.lens, JourneyLens.invalidResponse);
    expect(projection.rawStage, 'archived');
    expect(projection.verdicts['claim-1'], EvidenceVerdict.invalidResponse);
    expect(projection.rawVerdicts['claim-1'], 'MAYBE');
    expect(projection.checks.single.verdict, EvidenceVerdict.invalidResponse);
    expect(projection.checks.single.rawVerdict, 'CERTAIN');
    expect(projection.checks.single.receiptState, ReceiptState.invalidResponse);
    expect(projection.checks.single.rawReceiptState, 'SIGNED');
    expect(projection.parseIssues.map((issue) => issue.rawValue),
        containsAll(['flywheel.evidence-journey-projection/v9', 'archived']));
  });

  test('malformed gateway lists degrade to empty with parse issues', () {
    final projection = JourneyProjection.fromJson(_projection(
      factIds: 'fact-1',
      claimIds: const [1],
      checks: const {'check_id': 'check-1'},
      missingEvidence: null,
      nextActions: const ['inspect'],
      verdicts: const ['PASS'],
    ));

    expect(projection.factIds, isEmpty);
    expect(projection.claimIds, isEmpty);
    expect(projection.checks, isEmpty);
    expect(projection.verdicts, isEmpty);
    expect(projection.missingEvidence, isEmpty);
    expect(projection.nextActions, isEmpty);
    expect(
      projection.parseIssues.map((issue) => issue.field),
      containsAll([
        'fact_ids',
        'claim_ids',
        'checks',
        'verdicts',
        'missing_evidence',
        'next_actions',
      ]),
    );
  });

  test('receipt references never select MATCH when state is absent', () {
    final check = JourneyCheck.fromJson(const {
      'check_id': 'check-1',
      'claim_id': 'claim-1',
      'verdict': 'UNVERIFIABLE',
      'receipt_refs': ['receipts/existing.json'],
      'numerator': 0,
      'denominator': 1,
      'does_not_prove': 'authenticity',
    }, 'checks[0]');

    expect(check.receiptState, ReceiptState.invalidResponse);
    expect(check.rawReceiptState, isNull);
    expect(check.parseIssues.map((issue) => issue.field),
        contains('checks[0].receipt_state'));
  });

  test('grant acknowledgement export and public failure parse exactly', () {
    final proposal = GrantProposal.fromJson(const {
      'schema': 'flywheel.grant-proposal/v1',
      'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'action': 'check',
      'operation_sha256': _head,
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
      'event_head_sha256': _head,
      'event_sha256': _head,
      'projection_sha256': _projectionSha,
      'idempotent_replay': false,
      'operation_ref': 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'state': 'running',
    });
    final exported = JourneyExportResult.fromJson(const {
      'schema': 'flywheel.evidence-journey-export/v2',
      'profile': 'flywheel.evidence-journey-custody/v2',
      'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'source_event_head_sha256': _head,
      'final_event_head_sha256': _projectionSha,
      'final_projection_sha256': _head,
      'packet_ref': 'packets/journey',
      'packet_digest': _projectionSha,
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

  test('unsafe failure detail is not retained for display', () {
    const unsafeDetails = [
      r'C:\private\credential-token.txt',
      'error FiLe:private/input.json',
      'at (/etc/passwd)',
      'path={/Users/private/input.json}',
      'provider ghp_abcdefghijklmnopqrstuvwxyz123456',
      'password=abcdefghijklmnop',
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
