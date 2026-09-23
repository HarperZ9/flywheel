import 'package:flutter/material.dart';

import '../controllers/rowan_operation_controller.dart';
import '../models/rowan_run_budget.dart';
import '../theme/flywheel_theme.dart';

/// Workspace root, output tokens per call and the wall-time limit.
final class RowanBudgetRow extends StatelessWidget {
  const RowanBudgetRow({
    super.key,
    required this.rowan,
    required this.root,
    required this.tokens,
    required this.timeout,
  });

  final RowanOperationController rowan;
  final TextEditingController root, tokens, timeout;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final nativeCli = rowan.executionMode.isNativeCli;
    return Row(
      children: [
        Expanded(
          child: TextField(
            key: const Key('assistant-rowan-root'),
            controller: root,
            enabled: !rowan.active,
            style: fwMono(t, size: 11.5),
            decoration: const InputDecoration(
              isDense: true,
              labelText: 'Gateway workspace root',
            ),
            onChanged: rowan.setWorkspaceRoot,
          ),
        ),
        const SizedBox(width: FwLayout.s2),
        if (nativeCli)
          Text(
            'output tokens unsupported',
            style: fwMono(t, size: 10.5, color: t.inkFaint),
          )
        else
          RowanNumberField(
            key: const Key('assistant-rowan-max-tokens'),
            controller: tokens,
            enabled: !rowan.active,
            label: 'tokens',
            onSubmitted: rowan.setMaxTokens,
          ),
        const SizedBox(width: FwLayout.s2),
        RowanNumberField(
          key: const Key('assistant-rowan-timeout'),
          controller: timeout,
          enabled: !rowan.active,
          label: 'seconds',
          onSubmitted: rowan.setTimeoutSeconds,
        ),
      ],
    );
  }
}

/// The run budget: tool actions, total tokens and spend for the whole run.
///
/// An empty field means the engine default, shown as the hint at rest. Each
/// keystroke is applied, so a typed limit reaches the run without Enter. A
/// value out of range is named under its field and blocks the run until it
/// is fixed. The engine stops the run when a limit is reached and says which.
final class RowanRunBudgetRow extends StatefulWidget {
  const RowanRunBudgetRow({super.key, required this.rowan});

  final RowanOperationController rowan;

  @override
  State<RowanRunBudgetRow> createState() => _RowanRunBudgetRowState();
}

final class _RowanRunBudgetRowState extends State<RowanRunBudgetRow> {
  late final TextEditingController _actions, _tokens, _spend;

  @override
  void initState() {
    super.initState();
    final budget = widget.rowan.runBudget;
    _actions = TextEditingController(text: _text(budget.maxToolActions));
    _tokens = TextEditingController(text: _text(budget.maxUsageTokens));
    _spend = TextEditingController(text: dollarsFromMicros(budget.maxCostMicros));
  }

  static String _text(int? value) => value == null ? '' : '$value';

  @override
  void dispose() {
    _actions.dispose();
    _tokens.dispose();
    _spend.dispose();
    super.dispose();
  }

  RowanRunBudget _draft() => RowanRunBudget(
      maxToolActions: wholeNumberFromText(_actions.text),
      maxUsageTokens: wholeNumberFromText(_tokens.text),
      maxCostMicros: costMicrosFromDollars(_spend.text));

  void _apply() {
    widget.rowan.setRunBudget(_draft());
    setState(() {});
  }

  static String? _outside(int? value, (int, int) range, String name,
          String Function(int) show) =>
      value != null && (value < range.$1 || value > range.$2)
          ? '$name: ${show(range.$1)} to ${show(range.$2)}'
          : null;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final enabled = !widget.rowan.active;
    final draft = _draft();
    return Wrap(
      spacing: FwLayout.s2,
      runSpacing: FwLayout.s1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text('run budget', style: fwMono(t, size: 10.5, color: t.inkFaint)),
        _field(t, 'assistant-rowan-max-tool-actions', _actions, enabled,
            'tool actions', '${RowanRunBudget.defaultToolActions}',
            _outside(draft.maxToolActions, RowanRunBudget.toolActionsRange,
                'tool actions', groupedDigits)),
        _field(t, 'assistant-rowan-max-usage-tokens', _tokens, enabled,
            'run tokens', groupedDigits(RowanRunBudget.defaultUsageTokens),
            _outside(draft.maxUsageTokens, RowanRunBudget.usageTokensRange,
                'run tokens', groupedDigits)),
        _field(t, 'assistant-rowan-max-cost', _spend, enabled, r'spend $',
            dollarsFromMicros(RowanRunBudget.defaultCostMicros),
            _outside(draft.maxCostMicros, RowanRunBudget.costMicrosRange,
                'spend', (m) => '\$${dollarsFromMicros(m)}')),
      ],
    );
  }

  Widget _field(FwTokens t, String key, TextEditingController controller,
          bool enabled, String label, String hint, String? error) =>
      SizedBox(
        width: 120,
        child: TextField(
          key: Key(key),
          controller: controller,
          enabled: enabled,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: fwMono(t, size: 11.5),
          decoration: InputDecoration(
              isDense: true,
              labelText: label,
              hintText: hint,
              // The default shows at rest, not only after a click.
              floatingLabelBehavior: FloatingLabelBehavior.always,
              errorText: error,
              errorMaxLines: 2),
          onChanged: (_) => _apply(),
          onSubmitted: (_) => _apply(),
        ),
      );
}

/// The check the engine runs when the model says it is done.
///
/// Without one, the final answer can only be claimed. The engine runs it
/// through the exec gate, so the field is live only when exec is allowed.
final class RowanCheckCommandField extends StatefulWidget {
  const RowanCheckCommandField({super.key, required this.rowan});

  final RowanOperationController rowan;

  @override
  State<RowanCheckCommandField> createState() => _RowanCheckCommandFieldState();
}

final class _RowanCheckCommandFieldState extends State<RowanCheckCommandField> {
  late final TextEditingController _command =
      TextEditingController(text: widget.rowan.checkCommand ?? '');

  @override
  void dispose() {
    _command.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rowan = widget.rowan;
    final usable = rowan.allowExec && !rowan.executionMode.isNativeCli;
    return TextField(
      key: const Key('assistant-rowan-check-command'),
      controller: _command,
      enabled: usable && !rowan.active,
      style: fwMono(context.fw, size: 11.5),
      decoration: InputDecoration(
        isDense: true,
        labelText: 'check command',
        floatingLabelBehavior: FloatingLabelBehavior.always,
        hintText: usable
            ? 'runs when Rowan says it is done, e.g. python -m pytest -q'
            : null,
        // Helper text shows on a disabled field; a hint never does.
        helperText: usable ? null : checkCommandHelp(rowan, _command.text),
        helperMaxLines: 2,
      ),
      onChanged: (value) {
        rowan.setCheckCommand(value);
        setState(() {});
      },
    );
  }
}

/// Why the check command field is off, and whether a typed command runs.
String checkCommandHelp(RowanOperationController rowan, String typed) {
  final cli = rowan.executionMode.isNativeCli;
  if (typed.trim().isNotEmpty) {
    return cli
        ? 'native CLI sessions run no check: this command will not run'
        : 'exec is off: this check will not run';
  }
  return cli
      ? 'native CLI sessions run no check; the answer stays claimed'
      : 'allow exec to run a check; without one the answer stays claimed';
}

final class RowanNumberField extends StatelessWidget {
  const RowanNumberField({
    super.key,
    required this.controller,
    required this.enabled,
    required this.label,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final bool enabled;
  final String label;
  final ValueChanged<int> onSubmitted;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 96,
        child: TextField(
          controller: controller,
          enabled: enabled,
          keyboardType: TextInputType.number,
          style: fwMono(context.fw, size: 11.5),
          decoration: InputDecoration(isDense: true, labelText: label),
          onSubmitted: (value) {
            final parsed = int.tryParse(value.trim());
            if (parsed != null) onSubmitted(parsed);
          },
        ),
      );
}
