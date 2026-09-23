import 'package:flutter/material.dart';

import '../models/run_outcome.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

const _limitNames = {
  'model_calls': 'model call limit',
  'tool_actions': 'tool action limit',
  'usage_tokens': 'token budget',
  'cost_micros': 'spend limit',
};
const _signalNames = {
  'rate_limit': 'rate limit',
  'quota': 'quota',
  'billing': 'billing',
  'auth': 'sign-in',
  'overloaded': 'overloaded service',
};

String _count(int value) {
  final digits = '$value';
  final out = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write(',');
    out.write(digits[i]);
  }
  return out.toString();
}

String _dollars(int micros) => '\$${(micros / 1000000).toStringAsFixed(2)}';

String _signals(List<String> signals) =>
    signals.map((s) => _signalNames[s] ?? s).join(' or ');

/// One sentence on how the run ended against its budget.
String budgetHeadline(RunBudgetOutcome budget, {String? reason}) {
  switch (budget.status) {
    case 'unverifiable':
      return 'Budget record unverifiable (${budget.reason}). '
          'Treat the spend below as unknown.';
    case 'unrecorded':
      return reason == 'OPERATION_DEADLINE_EXCEEDED'
          ? 'Stopped: time limit reached before a budget record was written.'
          : 'No budget record in this trace.';
  }
  final tripped = budget.tripped;
  if (tripped == null) return 'Within the run budget.';
  if (tripped == 'wall_time') return 'Stopped by the run budget: time limit reached.';
  if (tripped == 'limit_signals') {
    return 'Stopped by the run budget: ${budget.limits['limit_signals']} steps '
        'in a row reported a limit error.';
  }
  final used = budget.used[tripped] ?? 0;
  final limit = budget.limits[tripped] ?? 0;
  final shown = tripped == 'cost_micros'
      ? '${_dollars(used)} of ${_dollars(limit)}'
      : '${_count(used)} of ${_count(limit)}';
  return 'Stopped by the run budget: ${_limitNames[tripped]} reached ($shown).';
}

/// What the run spent, with unreported usage named rather than guessed.
String budgetSpendLine(RunBudgetOutcome budget) {
  if (!budget.recorded) return '';
  final used = budget.used, limits = budget.limits, reporting = budget.reporting;
  final parts = [
    '${used['model_calls']} of ${limits['model_calls']} model calls',
    '${used['tool_actions']} of ${limits['tool_actions']} tool actions',
  ];
  final withTokens = reporting['calls_with_tokens'] ?? 0;
  final without = reporting['calls_without_tokens'] ?? 0;
  if (withTokens == 0 && without > 0) {
    parts.add('tokens not reported by the provider');
  } else {
    final gap = without > 0 ? ' ($without calls did not report)' : '';
    parts.add('${_count(used['usage_tokens'] ?? 0)} of '
        '${_count(limits['usage_tokens'] ?? 0)} tokens$gap');
  }
  parts.add((reporting['calls_with_cost'] ?? 0) == 0
      ? 'spend not reported by the provider'
      : 'spend ${_dollars(used['cost_micros'] ?? 0)} of '
          '${_dollars(limits['cost_micros'] ?? 0)}');
  return parts.join(' · ');
}

/// Steps that exited 0 while their output reported a limit error.
String? falseSuccessLine(RunBudgetOutcome budget, {String? reason}) {
  final n = budget.falseSuccessCount;
  if (n == 0) return null;
  final kinds = _signals(budget.falseSuccessSignals);
  final answer = reason == 'AGENT_FALSE_SUCCESS'
      ? ' The final answer was one of them, so the run is failed.'
      : '';
  return '$n step${n == 1 ? '' : 's'} exited 0 but reported a $kinds error; '
      'recorded as failed.$answer';
}

final class RowanRunOutcomeView extends StatelessWidget {
  const RowanRunOutcomeView({super.key, required this.outcome, this.reason});

  final RunOutcome outcome;
  final String? reason;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final budget = outcome.budget;
    final stopped = budget.status == 'stopped' || budget.status == 'unverifiable';
    final spend = budgetSpendLine(budget);
    final falseSuccess = falseSuccessLine(budget, reason: reason);
    return Column(
      key: const Key('rowan-run-outcome'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (stopped)
          HonestNull(budgetHeadline(budget, reason: reason))
        else
          Text(budgetHeadline(budget, reason: reason),
              style: fwMono(t, size: 11, color: t.inkSoft)),
        if (spend.isNotEmpty)
          Text(spend, style: fwMono(t, size: 10.5, color: t.inkFaint)),
        if (falseSuccess != null) ...[
          const SizedBox(height: FwLayout.s1),
          HonestNull(falseSuccess),
        ],
      ],
    );
  }
}
