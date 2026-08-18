import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _defaultCheck = <String, Object?>{
  'check_id': 'check-1',
  'claim_id': 'claim-1',
  'verdict': 'UNVERIFIABLE',
  'receipt_refs': ['receipts/check-1.json'],
  'receipt_state': 'present_unchecked',
  'numerator': 0,
  'denominator': 1,
  'does_not_prove': 'claim correctness',
};
const _defaultMissing = <String, Object?>{
  'kind': 'claim',
  'id': 'claim-1',
  'receipt_refs': ['receipts/pending'],
};
const _defaultAction = <String, Object?>{
  'action_id': 'inspect-1',
  'kind': 'inspect',
  'description': 'Inspect the receipt',
  'basis_refs': ['claim-1'],
};

Map<String, Object?> _projection({
  Object? factIds = const ['fact-1'],
  Object? claimIds = const ['claim-1'],
  Object? checks = const [_defaultCheck],
  Object? missingEvidence = const [_defaultMissing],
  Object? nextActions = const [_defaultAction],
  Object? verdicts = const {'claim-1': 'UNDECIDED'},
  Object? stage = 'running',
  Object? lens = 'Rescue',
  Object? conclusion,
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
      'conclusion': conclusion,
      'next_actions': nextActions,
      'detail': 'Server-owned diagnostic',
      'lens': lens,
      'presentation': const {'next_actions': <Object?>[]},
    };

class _DefensiveFixture extends DefensiveModel {
  _DefensiveFixture(super.parseIssues);
}

void main() {
  _projectionParsingTests();
  _closedStateTests();
  _defensiveInputTests();
  _immutabilityTests();
}

void _projectionParsingTests() {
  test('projection parses exact server-owned states and core fields', () {
    final projection = JourneyProjection.fromJson(_projection());

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
}

void _closedStateTests() {
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
}

void _defensiveInputTests() {
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

  test('unsafe verdict keys fail closed without entering maps or fields', () {
    const unsafeKey = r'C:\private\claim-secret';
    final projection = JourneyProjection.fromJson(_projection(
      verdicts: const {unsafeKey: 'PASS'},
    ));

    expect(projection.verdicts, isEmpty);
    expect(projection.rawVerdicts, isEmpty);
    expect(projection.parseIssues.single.field, 'verdicts.key');
    expect(projection.parseIssues.single.rawValue, '[redacted]');
    expect(projection.parseIssues.toString(), isNot(contains(unsafeKey)));
  });
}

void _immutabilityTests() {
  test('models copy caller collections and expose immutable collections', () {
    final facts = <Object?>['fact-1'];
    final verdicts = <String, Object?>{'claim-1': 'PASS'};
    final projection = JourneyProjection.fromJson(_projection(
      factIds: facts,
      verdicts: verdicts,
      conclusion: const {'summary': 'Bounded'},
    ));
    facts[0] = 'changed';
    verdicts['claim-1'] = 'FAIL';

    expect(projection.factIds, ['fact-1']);
    expect(projection.verdicts['claim-1'], EvidenceVerdict.pass);
    expect(() => projection.factIds.clear(), throwsUnsupportedError);
    expect(() => projection.verdicts.clear(), throwsUnsupportedError);
    for (final clear in <void Function()>[
      projection.claimIds.clear,
      projection.checks.clear,
      projection.missingEvidence.clear,
      projection.nextActions.clear,
      projection.checks.single.receiptRefs.clear,
      projection.missingEvidence.single.receiptRefs.clear,
      projection.nextActions.single.basisRefs.clear,
      projection.rawVerdicts.clear,
      projection.conclusion!.clear,
    ]) {
      expect(clear, throwsUnsupportedError);
    }

    final sourceIssues = <ParseIssue>[];
    final fixture = _DefensiveFixture(sourceIssues);
    sourceIssues.add((field: 'late', rawValue: 'mutation'));
    expect(fixture.parseIssues, isEmpty);
    expect(() => fixture.parseIssues.clear(), throwsUnsupportedError);

    final receiptRefs = <String>['receipts/one.json'];
    final check = JourneyCheck(
      checkId: 'check-1',
      claimId: 'claim-1',
      verdict: EvidenceVerdict.pass,
      rawVerdict: 'PASS',
      receiptRefs: receiptRefs,
      receiptState: ReceiptState.match,
      rawReceiptState: 'MATCH',
      numerator: 1,
      denominator: 1,
      doesNotProve: 'truth',
      parseIssues: const [],
    );
    receiptRefs.add('receipts/two.json');
    expect(check.receiptRefs, ['receipts/one.json']);
    expect(() => check.receiptRefs.clear(), throwsUnsupportedError);
  });

  test('long opaque public identifier remains displayable', () {
    const identifier =
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
    final failure = JourneyFailure.fromJson(const {
      'schema': 'flywheel.evidence-transport-error/v1',
      'error': {'code': 'PUBLIC_REFERENCE', 'message': identifier},
    });

    expect(failure.detail, identifier);
    expect(failure.invalidResponse, isFalse);
  });
}
