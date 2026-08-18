// plan_models.dart — neutral presentation of flywheel.prp/v2 metadata.
// Checkability names who could check a gate. It is never a pass verdict.

/// One validation gate inside a forged plan.
class PlanGate {
  final String check;
  final bool externallyCheckable;
  const PlanGate({required this.check, required this.externallyCheckable});

  factory PlanGate.fromJson(Map<String, dynamic> j) => PlanGate(
        check: j['check'] is String ? j['check'] as String : '',
        externallyCheckable: j['externally_checkable'] is bool
            ? j['externally_checkable'] as bool
            : false,
      );

  String get label => externallyCheckable ? 'checkable' : 'manual';
}

/// A forged plan: the criterion-bearing spec returned by POST /api/forge.
class ForgedPlan {
  final String goal;
  final String taskType;
  final int confidence;
  final String externalGateRatio;
  final int checkableGateCount;
  final int totalGateCount;
  final bool wellPosed; // did the goal state its own criterion?
  final List<PlanGate> gates;
  final String prompt; // the full rendered PRP
  final String prpId; // the server-held forge seal's id; drives the recheck
  final String? error;

  const ForgedPlan(
      {required this.goal,
      required this.taskType,
      required this.confidence,
      required this.externalGateRatio,
      required this.checkableGateCount,
      required this.totalGateCount,
      required this.wellPosed,
      required this.gates,
      required this.prompt,
      this.prpId = '',
      this.error});

  factory ForgedPlan.fromJson(Map<String, dynamic> j) => ForgedPlan(
        goal: j['goal'] is String ? j['goal'] as String : '',
        taskType: j['task_type'] is String ? j['task_type'] as String : '',
        confidence: j['confidence'] is int ? j['confidence'] as int : 0,
        externalGateRatio: j['external_gate_ratio'] is String
            ? j['external_gate_ratio'] as String
            : '0.000',
        checkableGateCount: j['gate_counts'] is Map &&
                (j['gate_counts'] as Map)['checkable'] is int
            ? (j['gate_counts'] as Map)['checkable'] as int
            : 0,
        totalGateCount:
            j['gate_counts'] is Map && (j['gate_counts'] as Map)['total'] is int
                ? (j['gate_counts'] as Map)['total'] as int
                : 0,
        wellPosed: j['well_posed'] is bool ? j['well_posed'] as bool : false,
        gates: List.unmodifiable((j['validation_gates'] is List
                ? j['validation_gates'] as List
                : const [])
            .whereType<Map<String, dynamic>>()
            .map(PlanGate.fromJson)),
        prompt: j['prompt'] is String ? j['prompt'] as String : '',
        prpId: j['prp_id'] is String ? j['prp_id'] as String : '',
        error: j['error'] is String ? j['error'] as String : null,
      );
}
