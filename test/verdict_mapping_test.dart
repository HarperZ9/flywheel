// Verdict mapping is the accept-path signal rendered as color. The client
// must never paint a completion state (DONE/COMPLETED) as the verified
// verdict the engine did not emit, and must render absence/unknown as the
// honest null (unverifiable), never as a definite DRIFT.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/workflow_models.dart';
import 'package:flywheel_desktop/models/science_models.dart';

void main() {
  group('WorkflowStep.verdict', () {
    test('DONE is a completion state, not the verified verdict', () {
      expect(WorkflowStep.fromJson({'status': 'DONE'}).verdict, 'unverifiable');
    });
    test('VERIFIED is the only verified verdict', () {
      expect(WorkflowStep.fromJson({'status': 'VERIFIED'}).verdict, 'verified');
    });
    test('FAILED and ERROR are drift', () {
      expect(WorkflowStep.fromJson({'status': 'FAILED'}).verdict, 'drift');
      expect(WorkflowStep.fromJson({'status': 'ERROR'}).verdict, 'drift');
    });
    test('a missing status is the honest null, not drift', () {
      expect(WorkflowStep.fromJson({}).verdict, 'unverifiable');
    });
    test('an unknown/unlisted status is the honest null, not drift', () {
      expect(WorkflowStep.fromJson({'status': 'whatever'}).verdict, 'unverifiable');
    });
  });

  group('WorkflowRun.verdict', () {
    test('COMPLETED means every stage ran, not that the run was verified', () {
      expect(WorkflowRun.fromJson({'status': 'COMPLETED'}).verdict, 'unverifiable');
    });
    test('VERIFIED is the verified verdict', () {
      expect(WorkflowRun.fromJson({'status': 'VERIFIED'}).verdict, 'verified');
    });
    test('FAILED is drift; a missing status is the honest null', () {
      expect(WorkflowRun.fromJson({'status': 'FAILED'}).verdict, 'drift');
      expect(WorkflowRun.fromJson({}).verdict, 'unverifiable');
    });
  });

  group('ClaimVerdict.verdict', () {
    test('a missing or unknown status is unverifiable, not drift', () {
      expect(ClaimVerdict.fromJson({}).verdict, 'unverifiable');
      expect(ClaimVerdict.fromJson({'status': 'huh'}).verdict, 'unverifiable');
    });
    test('MATCH is verified and DRIFT is drift', () {
      expect(ClaimVerdict.fromJson({'status': 'MATCH'}).verdict, 'verified');
      expect(ClaimVerdict.fromJson({'status': 'DRIFT'}).verdict, 'drift');
    });
  });
}
