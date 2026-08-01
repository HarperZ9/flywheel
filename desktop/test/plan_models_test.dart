// ForgedPlan: the typed reading of a flywheel.prp/v1 document. Checkability
// is the verdict: an oracle-checkable gate maps to verified, a manual gate to
// unverifiable. Parsing is defensive; an engine error body stays visible.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/plan_models.dart';

void main() {
  test('ForgedPlan parses a full flywheel.prp/v1 document', () {
    final plan = ForgedPlan.fromJson({
      'schema': 'flywheel.prp/v1',
      'goal': 'add a retry helper',
      'task_type': 'code',
      'confidence': 8,
      'external_gate_ratio': 1.0,
      'well_posed': true,
      'validation_gates': [
        {'check': 'pytest -q passes', 'externally_checkable': true},
        {'check': 'the one takeaway is present', 'externally_checkable': false},
      ],
      'prompt': '# PRP -- code task (confidence 8/10)',
    });
    expect(plan.goal, 'add a retry helper');
    expect(plan.taskType, 'code');
    expect(plan.confidence, 8);
    expect(plan.externalGateRatio, 1.0);
    expect(plan.wellPosed, isTrue);
    expect(plan.gates, hasLength(2));
    expect(plan.gates.first.label, 'oracle');
    expect(plan.gates.first.verdict, 'verified');
    expect(plan.gates.last.label, 'manual');
    expect(plan.gates.last.verdict, 'unverifiable');
    expect(plan.prompt, contains('PRP'));
    expect(plan.error, isNull);
  });

  test('ForgedPlan degrades on an empty document instead of crashing', () {
    final plan = ForgedPlan.fromJson(const {});
    expect(plan.goal, '');
    expect(plan.taskType, '');
    expect(plan.confidence, 0);
    expect(plan.externalGateRatio, 0.0);
    expect(plan.wellPosed, isFalse);
    expect(plan.gates, isEmpty);
    expect(plan.prompt, '');
  });

  test('ForgedPlan surfaces an engine error body', () {
    final plan = ForgedPlan.fromJson(const {'error': 'forge failed: boom'});
    expect(plan.error, 'forge failed: boom');
  });
}
