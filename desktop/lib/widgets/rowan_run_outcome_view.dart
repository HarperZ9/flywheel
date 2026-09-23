import 'package:flutter/material.dart';

import '../models/run_outcome.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'rowan_completion_summary.dart';

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
    return 'Stopped by the run budget: ${budget.limits['limit_signals']} limit '
        'errors in a row from the provider or the CLI.';
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
  final checks = budget.harnessChecks;
  final parts = [
    '${used['model_calls']} of ${limits['model_calls']} model calls',
    '${used['tool_actions']} of ${limits['tool_actions']} tool actions',
    // The check command is the harness's step and uses no tool action.
    if (checks > 0) '$checks check command run${checks == 1 ? '' : 's'}',
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

/// Success reports that came with a limit error in the provider's or the
/// CLI's own fields: a 2xx response whose body is a limit error, a CLI
/// session marked success after a limit event, a CLI that exits 0 with a
/// limit error on its stderr. Tool output and the answer are never read.
String? falseSuccessLine(RunBudgetOutcome budget, {String? reason}) {
  final kinds = _signals(budget.falseSuccessSignals);
  if (reason == 'AGENT_FALSE_SUCCESS') {
    return 'The provider or the CLI reported success next to a $kinds error, '
        'so the run is failed.';
  }
  final n = budget.falseSuccessCount;
  if (n == 0) return null;
  return '$n success report${n == 1 ? '' : 's'} from the provider or the CLI '
      'came with a $kinds error.';
}

/// The limit errors a limit-signal stop, or a false success, counted: where
/// each was reported (provider, cli_api_error, cli_result, cli_stderr), the
/// kind of limit and the vocabulary token that matched.
List<String> limitSignalLines(RunBudgetOutcome budget, {String? reason}) {
  if (budget.tripped != 'limit_signals' && reason != 'AGENT_FALSE_SUCCESS') {
    return const [];
  }
  return [
    for (final step in budget.limitSignalSteps)
      '${step.tool}: ${_signalNames[step.signal] ?? step.signal}, '
          'matched "${step.match}"',
  ];
}

const _visibleItems = 8;

/// How a finished run ended: what a check confirmed first, then its spend.
final class RowanRunOutcomeView extends StatelessWidget {
  const RowanRunOutcomeView({super.key, required this.outcome, this.reason});

  final RunOutcome outcome;
  final String? reason;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final completion = outcome.completion;
    final budget = outcome.budget;
    final stopped = budget.status == 'stopped' || budget.status == 'unverifiable';
    final spend = budgetSpendLine(budget);
    final falseSuccess = falseSuccessLine(budget, reason: reason);
    final counted = limitSignalLines(budget, reason: reason);
    final hidden = completion.items.length - _visibleItems + completion.itemsOmitted;
    return Column(
      key: const Key('rowan-run-outcome'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // A live region, so a screen reader announces how the run ended
        // when the outcome appears.
        Semantics(
          key: const Key('rowan-outcome-headline'),
          liveRegion: true,
          child: Row(children: [
            if (completion.recorded) ...[
              VerdictPill(completion.verdict!,
                  status: completionVerdictStatus(completion.verdict)),
              const SizedBox(width: FwLayout.s2),
            ],
            Expanded(
                child: Text(completionHeadline(completion),
                    key: const Key('rowan-completion-headline'),
                    style: TextStyle(fontSize: 12, color: t.ink))),
          ]),
        ),
        if (completion.recorded) ...[
          Text(completionSplit(completion),
              style: fwMono(t, size: 11, color: t.inkSoft)),
          for (final item in completion.items.take(_visibleItems))
            Text(completionItemLine(item),
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
          if (hidden > 0)
            Text('and $hidden more',
                style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ],
        if (completion.unbackedSuccessClaim) HonestNull(unbackedClaimLine),
        const SizedBox(height: FwLayout.s1),
        if (stopped)
          HonestNull(budgetHeadline(budget, reason: reason))
        else
          Text(budgetHeadline(budget, reason: reason),
              style: fwMono(t, size: 11, color: t.inkSoft)),
        if (spend.isNotEmpty)
          Text(spend, style: fwMono(t, size: 10.5, color: t.inkFaint)),
        for (final line in counted)
          Text(line,
              key: const Key('rowan-limit-signal-step'),
              style: fwMono(t, size: 10.5, color: t.inkSoft)),
        if (falseSuccess != null) ...[
          const SizedBox(height: FwLayout.s1),
          HonestNull(falseSuccess),
        ],
      ],
    );
  }
}
