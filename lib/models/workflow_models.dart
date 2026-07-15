// workflow_models.dart — typed models for profiles and staged workflow runs.
// Gate values in a profile are requested defaults, never authorizations:
// the engine's runtime gate enforces what the caller actually granted.

/// A profile manifest (GET /api/profiles).
class ProfileManifest {
  final String name;
  final String description;
  final String? workflow;
  final bool wantsWrite;
  final bool wantsExec;
  final int maxSteps;
  final List<String> tools;
  final List<String> planning;
  final List<String> surface;
  final String indexScope;

  ProfileManifest(
      {required this.name,
      required this.description,
      this.workflow,
      required this.wantsWrite,
      required this.wantsExec,
      required this.maxSteps,
      this.tools = const [],
      this.planning = const [],
      this.surface = const [],
      this.indexScope = ''});

  factory ProfileManifest.fromJson(Map<String, dynamic> j) {
    final gates = (j['gates'] ?? {}) as Map<String, dynamic>;
    List<String> strs(dynamic v) =>
        v is List ? v.map((e) => '$e').toList() : const [];
    return ProfileManifest(
      name: j['name'] ?? '',
      description: j['description'] ?? '',
      workflow: j['workflow'],
      wantsWrite: gates['allow_write'] ?? false,
      wantsExec: gates['allow_exec'] ?? false,
      maxSteps: j['max_steps'] ?? 6,
      tools: strs(j['tools']),
      planning: strs(j['planning']),
      surface: strs(j['surface']),
      indexScope: j['index_scope'] ?? '',
    );
  }
}

/// A workflow definition summary (GET /api/workflows).
class WorkflowDef {
  final String name;
  final String description;
  final List<String> stepNames;

  WorkflowDef(
      {required this.name,
      required this.description,
      required this.stepNames});

  factory WorkflowDef.fromJson(Map<String, dynamic> j) => WorkflowDef(
        name: j['name'] ?? '',
        description: j['description'] ?? '',
        stepNames: (j['steps'] is List)
            ? (j['steps'] as List)
                .whereType<Map<String, dynamic>>()
                .map((s) => '${s['name'] ?? ''}')
                .toList()
            : const [],
      );
}

/// The workflow roster: definitions plus recent persisted runs.
class WorkflowRoster {
  final List<WorkflowDef> workflows;
  final List<Map<String, dynamic>> runs;

  WorkflowRoster({required this.workflows, required this.runs});

  factory WorkflowRoster.fromJson(Map<String, dynamic> j) => WorkflowRoster(
        workflows: ((j['workflows'] ?? []) as List)
            .map((e) => WorkflowDef.fromJson(e as Map<String, dynamic>))
            .toList(),
        runs: ((j['runs'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList(),
      );
}

/// One executed step inside a workflow run.
class WorkflowStep {
  final String name;
  final String kind;
  final String status; // DONE | VERIFIED | UNVERIFIABLE | FAILED | ERROR
  final String excerpt;
  final String note;
  final String checkpoint;
  final bool? integrityClean;

  WorkflowStep(
      {required this.name,
      required this.kind,
      required this.status,
      required this.excerpt,
      required this.note,
      required this.checkpoint,
      this.integrityClean});

  factory WorkflowStep.fromJson(Map<String, dynamic> j) => WorkflowStep(
        name: j['name'] ?? '',
        kind: j['kind'] ?? '',
        status: j['status'] ?? '',
        excerpt: j['excerpt'] ?? '',
        note: j['note'] ?? '',
        checkpoint: j['checkpoint'] ?? '',
        integrityClean: j['integrity_clean'],
      );

  /// Maps the step status onto the verdict palette. DONE means the step RAN,
  /// not that an external check accepted it, so only VERIFIED earns the accept
  /// color; FAILED/ERROR are drift; DONE, UNVERIFIABLE, and any absent/unknown
  /// status are the honest null.
  String get verdict => switch (status) {
        'VERIFIED' => 'verified',
        'DRIFT' || 'FAILED' || 'ERROR' => 'drift',
        _ => 'unverifiable',
      };
}

/// A completed workflow run (POST /api/workflow).
class WorkflowRun {
  final String workflow;
  final String endpoint;
  final String status;
  final String chainHash;
  final List<WorkflowStep> steps;
  final String? error;

  WorkflowRun(
      {required this.workflow,
      required this.endpoint,
      required this.status,
      required this.chainHash,
      required this.steps,
      this.error});

  factory WorkflowRun.fromJson(Map<String, dynamic> j) => WorkflowRun(
        workflow: j['workflow'] ?? '',
        endpoint: j['endpoint'] ?? '',
        status: j['status'] ?? '',
        chainHash: j['chain_hash'] ?? '',
        steps: ((j['steps'] ?? []) as List)
            .map((e) => WorkflowStep.fromJson(e as Map<String, dynamic>))
            .toList(),
        error: j['error'],
      );

  /// COMPLETED means every stage executed, not that the run was verified: only
  /// VERIFIED earns the accept color. FAILED/ERROR are drift; COMPLETED,
  /// UNVERIFIED, and any absent/unknown status are the honest null.
  String get verdict => switch (status) {
        'VERIFIED' => 'verified',
        'DRIFT' || 'FAILED' || 'ERROR' => 'drift',
        _ => 'unverifiable',
      };
}
