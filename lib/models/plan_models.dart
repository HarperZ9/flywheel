// plan_models.dart — typed reading of a forged plan (flywheel.prp/v1).
// Checkability IS the verdict here: a gate an external oracle can run maps to
// verified, a subjective gate to unverifiable. The confidence score is the
// engine's, grounded in that ratio — never recomputed or dressed up client-side.

/// One validation gate inside a forged plan.
class PlanGate {
  final String check;
  final bool externallyCheckable;
  const PlanGate({required this.check, required this.externallyCheckable});

  factory PlanGate.fromJson(Map<String, dynamic> j) => PlanGate(
        check: j['check'] ?? '',
        externallyCheckable: j['externally_checkable'] ?? false,
      );

  String get label => externallyCheckable ? 'oracle' : 'manual';
  String get verdict => externallyCheckable ? 'verified' : 'unverifiable';
}

/// A forged plan: the criterion-bearing spec returned by POST /api/forge.
class ForgedPlan {
  final String goal;
  final String taskType;
  final int confidence; // 1..10, scored by external-checkability
  final double externalGateRatio; // 0..1, fraction of oracle-runnable gates
  final bool wellPosed; // did the goal state its own criterion?
  final List<PlanGate> gates;
  final String prompt; // the full rendered PRP
  final String? error;

  const ForgedPlan(
      {required this.goal,
      required this.taskType,
      required this.confidence,
      required this.externalGateRatio,
      required this.wellPosed,
      required this.gates,
      required this.prompt,
      this.error});

  factory ForgedPlan.fromJson(Map<String, dynamic> j) => ForgedPlan(
        goal: j['goal'] ?? '',
        taskType: j['task_type'] ?? '',
        confidence: j['confidence'] is num ? (j['confidence'] as num).toInt() : 0,
        externalGateRatio: j['external_gate_ratio'] is num
            ? (j['external_gate_ratio'] as num).toDouble()
            : 0.0,
        wellPosed: j['well_posed'] ?? false,
        gates: ((j['validation_gates'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .map(PlanGate.fromJson)
            .toList(),
        prompt: j['prompt'] ?? '',
        error: j['error'],
      );
}
