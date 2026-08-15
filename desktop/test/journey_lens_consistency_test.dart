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
}
