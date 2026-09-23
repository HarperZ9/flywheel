// rowan_run_budget.dart -- the owner's per-run limits for one Rowan run.
//
// The engine owns the policy (harness/run_budget.py): it applies these
// overrides, fills the rest from its defaults, stops the run at the limit
// and records why. This class only carries what the owner changed, so an
// unset field means "the engine default", never zero. The constants below
// mirror the engine's defaults and bounds for display; the test
// tests/test_rowan_run_budget_mirror.py fails if the two drift.

final class RowanRunBudget {
  static const defaultToolActions = 24;
  static const defaultUsageTokens = 200000;
  static const defaultCostMicros = 2000000;
  static const toolActionsRange = (0, 200);
  static const usageTokensRange = (1000, 10000000);
  static const costMicrosRange = (10000, 1000000000);

  final int? maxToolActions, maxUsageTokens, maxCostMicros;

  const RowanRunBudget(
      {this.maxToolActions, this.maxUsageTokens, this.maxCostMicros});

  bool get isDefault =>
      maxToolActions == null && maxUsageTokens == null && maxCostMicros == null;

  int get toolActions => maxToolActions ?? defaultToolActions;
  int get usageTokens => maxUsageTokens ?? defaultUsageTokens;
  int get costMicros => maxCostMicros ?? defaultCostMicros;

  /// The operation's `run_budget` field: only the limits the owner set.
  Map<String, Object?>? toWire() => isDefault
      ? null
      : {
          if (maxToolActions != null) 'max_tool_actions': maxToolActions,
          if (maxUsageTokens != null) 'max_usage_tokens': maxUsageTokens,
          if (maxCostMicros != null) 'max_cost_micros': maxCostMicros,
        };

  /// The fields as a panel shows this budget: empty where the default applies.
  RowanRunBudgetText get text => (
        actions: maxToolActions == null ? '' : '$maxToolActions',
        tokens: maxUsageTokens == null ? '' : '$maxUsageTokens',
        spend: dollarsFromMicros(maxCostMicros),
      );

  /// The first out-of-range field, or null when every set field is valid.
  String? get invalidField {
    bool outside(int? value, (int, int) range) =>
        value != null && (value < range.$1 || value > range.$2);
    if (outside(maxToolActions, toolActionsRange)) return 'max_tool_actions';
    if (outside(maxUsageTokens, usageTokensRange)) return 'max_usage_tokens';
    if (outside(maxCostMicros, costMicrosRange)) return 'max_cost_micros';
    return null;
  }

  RowanRunBudget withToolActions(int? value) => RowanRunBudget(
      maxToolActions: value,
      maxUsageTokens: maxUsageTokens,
      maxCostMicros: maxCostMicros);

  RowanRunBudget withUsageTokens(int? value) => RowanRunBudget(
      maxToolActions: maxToolActions,
      maxUsageTokens: value,
      maxCostMicros: maxCostMicros);

  RowanRunBudget withCostMicros(int? value) => RowanRunBudget(
      maxToolActions: maxToolActions,
      maxUsageTokens: maxUsageTokens,
      maxCostMicros: value);

  @override
  bool operator ==(Object other) =>
      other is RowanRunBudget &&
      other.maxToolActions == maxToolActions &&
      other.maxUsageTokens == maxUsageTokens &&
      other.maxCostMicros == maxCostMicros;

  @override
  int get hashCode => Object.hash(maxToolActions, maxUsageTokens, maxCostMicros);
}

/// The three budget fields as the owner typed them. The controller holds
/// this while a field is out of range, so a rebuilt panel shows the same text
/// and the same error that make start() refuse.
typedef RowanRunBudgetText = ({String actions, String tokens, String spend});

extension RowanRunBudgetTextParse on RowanRunBudgetText {
  /// The limits the text sets. Unparsable text reads as -1, out of range.
  RowanRunBudget get budget => RowanRunBudget(
      maxToolActions: wholeNumberFromText(actions),
      maxUsageTokens: wholeNumberFromText(tokens),
      maxCostMicros: costMicrosFromDollars(spend));
}

/// Dollars typed by the owner to whole micro-dollars, or null when unset.
/// Thousands separators are accepted; anything else unparsable is -1, which
/// no range admits.
int? costMicrosFromDollars(String text) {
  final trimmed = text.trim().replaceFirst(r'$', '').replaceAll(',', '');
  if (trimmed.isEmpty) return null;
  final dollars = double.tryParse(trimmed);
  if (dollars == null || dollars.isNaN || dollars.isInfinite) return -1;
  return (dollars * 1000000).round();
}

/// A whole number typed by the owner, or null when unset. Thousands
/// separators are accepted, so "200,000" reads as the card prints it.
int? wholeNumberFromText(String text) {
  final trimmed = text.trim().replaceAll(RegExp(r'[,_ ]'), '');
  return trimmed.isEmpty ? null : int.tryParse(trimmed) ?? -1;
}

/// Micro-dollars as the owner typed them: at least two decimals and no
/// rounding, so a stored limit of 0.015 is shown as 0.015, not 0.01.
String dollarsFromMicros(int? micros) {
  if (micros == null) return '';
  var text = (micros / 1000000).toStringAsFixed(6);
  while (text.endsWith('0') && text.length - text.indexOf('.') > 3) {
    text = text.substring(0, text.length - 1);
  }
  return text;
}

/// A whole number with thousands separators, as the card prints limits.
String groupedDigits(int value) {
  final digits = '${value.abs()}';
  final out = StringBuffer(value < 0 ? '-' : '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write(',');
    out.write(digits[i]);
  }
  return out.toString();
}
