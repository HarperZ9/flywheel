// A bounded projection of Relay state, never a replacement for its run store.
enum AssistantTaskState {
  submitted,
  running,
  completed,
  failed,
  interrupted,
  unknown
}

enum AssistantTaskAssurance { unchecked, reportedIntact, held }

bool isAssistantRunRef(Object? value) =>
    value is String && RegExp(r'^[0-9a-f]{16}$').hasMatch(value);

class AssistantTask {
  const AssistantTask(this.runId, this.state,
      {this.assurance = AssistantTaskAssurance.unchecked,
      this.checkpoint,
      this.steps,
      this.readFailed = false});

  final String runId;
  final AssistantTaskState state;
  final AssistantTaskAssurance assurance;
  final String? checkpoint;
  final int? steps;
  final bool readFailed;

  bool get active =>
      state == AssistantTaskState.submitted ||
      state == AssistantTaskState.running;

  String get label => switch (state) {
        AssistantTaskState.submitted => 'Submitted',
        AssistantTaskState.running => 'Running',
        AssistantTaskState.completed => 'Execution completed',
        AssistantTaskState.failed => 'Execution failed',
        AssistantTaskState.interrupted => 'Interrupted',
        AssistantTaskState.unknown => 'State unknown',
      };

  String get evidenceLabel => switch (assurance) {
        AssistantTaskAssurance.unchecked => 'Receipt assurance unavailable',
        AssistantTaskAssurance.reportedIntact =>
          'Relay reports receipt integrity',
        AssistantTaskAssurance.held => 'Result needs review',
      };

  factory AssistantTask.unknown(String runId) =>
      AssistantTask(runId, AssistantTaskState.unknown, readFailed: true);

  AssistantTask get resultUnavailable =>
      AssistantTask(runId, state, steps: steps, readFailed: true);

  static AssistantTask? fromStatus(Object? raw, {String? expectedRef}) {
    if (raw is! Map || !isAssistantRunRef(raw['run_id'])) return null;
    final id = raw['run_id'] as String;
    if (expectedRef != null && id != expectedRef) return null;
    if (raw.containsKey('error') && raw['state'] != 'error') {
      return AssistantTask.unknown(id);
    }
    final state = switch (raw['state']) {
      'running' => AssistantTaskState.running,
      'done' => AssistantTaskState.completed,
      'error' => AssistantTaskState.failed,
      'interrupted' => AssistantTaskState.interrupted,
      _ => AssistantTaskState.unknown,
    };
    final steps = raw['steps'];
    return AssistantTask(id, state,
        steps: steps is int && steps >= 0 && steps <= 1000000 ? steps : null);
  }

  AssistantTask withResult(Object? raw) {
    if (raw is Map &&
        ((raw.containsKey('run_id') && raw['run_id'] != runId) ||
            (raw.containsKey('state') && raw['state'] != 'done') ||
            (raw.containsKey('error') && raw['state'] == 'done'))) {
      return AssistantTask.unknown(runId);
    }
    if (raw is! Map ||
        raw.containsKey('error') ||
        raw['run_id'] != runId ||
        raw['state'] != 'done' ||
        raw['result'] is! Map) {
      return resultUnavailable;
    }
    final result = raw['result'] as Map;
    final checkpoint = result['checkpoint'];
    final valid = result['verified'] is bool &&
        result['chain_ok'] is bool &&
        result['final_answer'] is bool &&
        checkpoint is String &&
        RegExp(r'^[0-9a-f]{64}$').hasMatch(checkpoint);
    if (!valid) return resultUnavailable;
    final intact = result['verified'] == true &&
        result['chain_ok'] == true &&
        result['final_answer'] == true;
    return AssistantTask(runId, AssistantTaskState.completed,
        steps: steps,
        checkpoint: checkpoint,
        assurance: intact
            ? AssistantTaskAssurance.reportedIntact
            : AssistantTaskAssurance.held);
  }
}
