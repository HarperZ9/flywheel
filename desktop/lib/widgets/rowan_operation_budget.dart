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
/// An empty field means the engine default, shown as the hint. The engine
/// stops the run when a limit is reached and says which one.
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
    final cost = budget.maxCostMicros;
    _spend = TextEditingController(
        text: cost == null ? '' : (cost / 1000000).toStringAsFixed(2));
  }

  static String _text(int? value) => value == null ? '' : '$value';

  static int? _whole(String text) {
    final trimmed = text.trim();
    return trimmed.isEmpty ? null : int.tryParse(trimmed) ?? -1;
  }

  @override
  void dispose() {
    _actions.dispose();
    _tokens.dispose();
    _spend.dispose();
    super.dispose();
  }

  void _submit() {
    final rowan = widget.rowan;
    rowan.setRunBudget(rowan.runBudget
        .withToolActions(_whole(_actions.text))
        .withUsageTokens(_whole(_tokens.text))
        .withCostMicros(costMicrosFromDollars(_spend.text)));
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final enabled = !widget.rowan.active;
    return Wrap(
      spacing: FwLayout.s2,
      runSpacing: FwLayout.s1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text('run budget', style: fwMono(t, size: 10.5, color: t.inkFaint)),
        _field(t, 'assistant-rowan-max-tool-actions', _actions, enabled,
            'tool actions', '${RowanRunBudget.defaultToolActions}'),
        _field(t, 'assistant-rowan-max-usage-tokens', _tokens, enabled,
            'run tokens', '${RowanRunBudget.defaultUsageTokens}'),
        _field(t, 'assistant-rowan-max-cost', _spend, enabled, r'spend $',
            (RowanRunBudget.defaultCostMicros / 1000000).toStringAsFixed(2)),
      ],
    );
  }

  Widget _field(FwTokens t, String key, TextEditingController controller,
          bool enabled, String label, String hint) =>
      SizedBox(
        width: 104,
        child: TextField(
          key: Key(key),
          controller: controller,
          enabled: enabled,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: fwMono(t, size: 11.5),
          decoration: InputDecoration(
              isDense: true, labelText: label, hintText: hint),
          onSubmitted: (_) => _submit(),
        ),
      );
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
