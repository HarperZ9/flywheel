// run_outcome.dart -- the content-free run outcome on a terminal projection.
//
// The gateway derives this block from the private trace at terminal time and
// recomputes it on every read (harness/gateway_run_outcome.py). The desktop
// only parses it. A shape it does not recognise makes the whole projection
// invalid, the same rule the effect evidence block follows, because the
// projection hash covers it.

import 'run_completion_outcome.dart';

export 'run_completion_outcome.dart';

const runOutcomeSchema = 'flywheel.gateway-run-outcome/v1';

const _limitKeys = {
  'model_calls',
  'tool_actions',
  'usage_tokens',
  'cost_micros',
  'limit_signals',
  'wall_time_ms',
};
const _usedKeys = {
  'model_calls',
  'tool_actions',
  'usage_tokens',
  'cost_micros',
  'wall_time_ms',
};
const _reportingKeys = {
  'calls_with_tokens',
  'calls_without_tokens',
  'calls_with_cost',
};
const runBudgetTrips = {
  'model_calls',
  'tool_actions',
  'usage_tokens',
  'cost_micros',
  'limit_signals',
  'wall_time',
};
const runLimitSignals = {'rate_limit', 'quota', 'billing', 'auth', 'overloaded'};

Never _invalid() => throw const FormatException('Run outcome is invalid');

Map<String, dynamic> _map(Object? value) {
  if (value is! Map) _invalid();
  if (value.keys.any((key) => key is! String)) _invalid();
  return Map<String, dynamic>.from(value);
}

void _fields(Map<String, dynamic> value, Set<String> fields) {
  if (value.length != fields.length || !value.keys.every(fields.contains)) {
    _invalid();
  }
}

Map<String, int> _naturals(Object? raw, Set<String> keys) {
  final value = _map(raw);
  _fields(value, keys);
  if (value.values.any((item) => item is! int || item < 0)) _invalid();
  return Map<String, int>.unmodifiable(value.cast<String, int>());
}

final class RunOutcome {
  final String terminalState;
  final RunCompletionOutcome completion;
  final RunBudgetOutcome budget;

  const RunOutcome._(this.terminalState, this.completion, this.budget);

  factory RunOutcome.fromJson(Object? raw, {required String terminalState}) {
    final value = _map(raw);
    _fields(value, const {'schema', 'terminal_state', 'completion', 'budget'});
    if (value['schema'] != runOutcomeSchema ||
        value['terminal_state'] != terminalState) {
      _invalid();
    }
    final completion = RunCompletionOutcome.fromJson(value['completion']);
    // A run that did not complete cannot have a verified final answer.
    if (terminalState == 'failed' &&
        completion.items.any((item) =>
            item.kind == 'final_answer' && item.status == 'verified')) {
      _invalid();
    }
    return RunOutcome._(terminalState, completion,
        RunBudgetOutcome.fromJson(value['budget']));
  }
}

/// What the run spent against its limits, or why that cannot be shown.
final class RunBudgetOutcome {
  /// within_limits, stopped, unverifiable or unrecorded.
  final String status;
  final String? tripped, reason;
  final Map<String, int> limits, used, reporting;
  final int falseSuccessCount;
  final List<String> falseSuccessSignals;

  const RunBudgetOutcome._(this.status, this.tripped, this.reason, this.limits,
      this.used, this.reporting, this.falseSuccessCount, this.falseSuccessSignals);

  bool get recorded => status == 'within_limits' || status == 'stopped';

  factory RunBudgetOutcome.fromJson(Object? raw) {
    final value = _map(raw);
    final status = value['status'];
    if (status == 'unrecorded') {
      _fields(value, const {'status'});
      return const RunBudgetOutcome._(
          'unrecorded', null, null, {}, {}, {}, 0, []);
    }
    if (status == 'unverifiable') {
      _fields(value, const {'status', 'reason', 'record_sequence'});
      final reason = value['reason'];
      if (reason is! String ||
          !RegExp(r'^[A-Z][A-Z0-9_]{0,63}$').hasMatch(reason) ||
          value['record_sequence'] is! int) {
        _invalid();
      }
      return RunBudgetOutcome._(
          'unverifiable', null, reason, const {}, const {}, const {}, 0, const []);
    }
    return _recorded(value);
  }

  static RunBudgetOutcome _recorded(Map<String, dynamic> value) {
    _fields(value, const {
      'status',
      'tripped',
      'limits',
      'used',
      'reporting',
      'false_success_count',
      'false_success_signals',
      'record_sequence',
    });
    final tripped = value['tripped'];
    final status = value['status'];
    if ((tripped != null && !runBudgetTrips.contains(tripped)) ||
        status != (tripped == null ? 'within_limits' : 'stopped') ||
        value['record_sequence'] is! int) {
      _invalid();
    }
    final count = value['false_success_count'];
    final signals = value['false_success_signals'];
    if (count is! int ||
        count < 0 ||
        signals is! List ||
        signals.any((s) => s is! String || !runLimitSignals.contains(s))) {
      _invalid();
    }
    return RunBudgetOutcome._(
        status as String,
        tripped as String?,
        null,
        _naturals(value['limits'], _limitKeys),
        _naturals(value['used'], _usedKeys),
        _naturals(value['reporting'], _reportingKeys),
        count,
        List<String>.unmodifiable(signals.cast<String>()));
  }
}
