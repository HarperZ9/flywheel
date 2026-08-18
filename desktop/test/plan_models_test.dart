// ForgedPlan: neutral reading of flywheel.prp/v2 checkability metadata.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/plan_models.dart';

void main() {
  test('ForgedPlan parses v2 counts and neutral gate labels', () {
    final plan = ForgedPlan.fromJson({
      'schema': 'flywheel.prp/v2',
      'goal': 'add a retry helper',
      'task_type': 'code',
      'confidence': 8,
      'external_gate_ratio': '0.500',
      'gate_counts': {'checkable': 1, 'total': 2},
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
    expect(plan.externalGateRatio, '0.500');
    expect(plan.checkableGateCount, 1);
    expect(plan.totalGateCount, 2);
    expect(plan.wellPosed, isTrue);
    expect(plan.gates, hasLength(2));
    expect(plan.gates.first.label, 'checkable');
    expect(plan.gates.last.label, 'manual');
    expect(plan.gates.map((gate) => gate.label), ['checkable', 'manual']);
    expect(plan.prompt, contains('PRP'));
    expect(plan.error, isNull);
  });

  test('ForgedPlan degrades on an empty document instead of crashing', () {
    final plan = ForgedPlan.fromJson(const {});
    expect(plan.goal, '');
    expect(plan.taskType, '');
    expect(plan.confidence, 0);
    expect(plan.externalGateRatio, '0.000');
    expect(plan.checkableGateCount, 0);
    expect(plan.totalGateCount, 0);
    expect(plan.wellPosed, isFalse);
    expect(plan.gates, isEmpty);
    expect(plan.prompt, '');
  });

  test('ForgedPlan surfaces an engine error body', () {
    final plan = ForgedPlan.fromJson(const {'error': 'forge failed: boom'});
    expect(plan.error, 'forge failed: boom');
  });
}
