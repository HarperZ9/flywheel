// rowan_completion_summary.dart -- the words Rowan uses for how a run ended.
//
// The rule these functions keep: "Done" is said only when every deliverable
// passed a named check. Work that rests on the model's word is called
// claimed, and the summary says how much of it there is. Pure functions, so
// the rule is tested without a widget tree.

import '../models/run_completion_outcome.dart';

/// The status colour for a completion verdict (color is verdict-only).
String completionVerdictStatus(String? verdict) => switch (verdict) {
      'verified' => 'verified',
      'failed' => 'drift',
      _ => 'unverifiable',
    };

String _deliverables(int n) => n == 1 ? 'deliverable' : 'deliverables';

/// The first line of a finished run's summary.
String completionHeadline(RunCompletionOutcome completion) {
  if (completion.status == 'unverifiable') {
    return 'Completion unverifiable (${completion.reason}). '
        'Nothing in this run is confirmed.';
  }
  if (!completion.recorded) {
    return 'No completion record for this run. Nothing in it is confirmed.';
  }
  final total = completion.counts.values.fold<int>(0, (a, b) => a + b);
  final failed = completion.counts['failed'] ?? 0;
  final claimed = completion.counts['claimed'] ?? 0;
  if (completion.done) return 'Done. Every deliverable passed a check.';
  // The answer item is always listed, so a run_state failure is always seen.
  // A check the step budget never reached is a run that did not finish too.
  final stopped = completion.items.any((i) =>
      i.status == 'failed' && (i.check == 'run_state' || i.detail == 'not_run'));
  final checked = failed - (stopped ? 1 : 0);
  if (stopped && checked == 0) {
    return 'Not done: the run stopped before it finished.';
  }
  if (stopped) {
    return 'Not done: the run stopped before it finished, and $checked of '
        '$total ${_deliverables(total)} failed a check.';
  }
  if (failed > 0) {
    return 'Not done: $failed of $total ${_deliverables(total)} failed a check.';
  }
  return 'Finished, not verified: no check covered $claimed of $total '
      '${_deliverables(total)}.';
}

/// The split the summary leads with.
String completionSplit(RunCompletionOutcome completion) {
  final c = completion.counts;
  return 'Verified ${c['verified'] ?? 0} · Claimed ${c['claimed'] ?? 0} · '
      'Failed ${c['failed'] ?? 0}';
}

const _fileLines = {
  'matches': 'File written: matches the hash recorded at write time.',
  'missing': 'File written: missing at the end of the run.',
  'changed_after_write': 'File written: changed after it was written.',
  'no_recorded_hash': 'File written: claimed, no hash was recorded.',
  'changed_by_command':
      'File changed by a command: claimed, nothing recorded what it holds.',
};

/// One line per deliverable, naming the check behind its status.
String completionItemLine(CompletionItem item) {
  if (item.kind == 'file') return _fileLines[item.detail] ?? 'File written.';
  return switch ((item.status, item.check, item.detail)) {
    ('verified', 'test_command', _) => 'Answer: the check command passed.',
    ('verified', 'acceptance_criteria', _) =>
      'Answer: the acceptance criteria passed.',
    ('failed', 'run_state', final reason) =>
      'Answer: the run did not complete ($reason).',
    ('failed', 'test_command', 'not_run') => 'Answer: $unrunCheckNote.',
    ('failed', _, 'integrity_not_clean') =>
      'Answer: the check passed on a run that touched its own check; '
          'not trusted.',
    ('failed', _, _) => 'Answer: the check did not pass.',
    _ => 'Answer: claimed, no check ran. A check command would verify it.',
  };
}

/// The engine's UNRUN_CHECK_NOTE (harness/gateway_agent_native_tools.py),
/// word for word: the step budget ran out before the check command ran.
/// tests/test_run_completion_integrity.py fails if the two drift.
const unrunCheckNote = 'step budget exhausted; the test command never ran, '
    'so this is unwitnessed, not an observed failure';

/// Shown when the answer says it succeeded and nothing backs that.
const unbackedClaimLine =
    'The answer says it succeeded, but no check backs that claim.';
