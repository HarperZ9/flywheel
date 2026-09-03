// effort_dial.dart — the one knob, as a control the operator can reach.
//
// The engine has carried four named dials since July and stamps the resolved
// one into every run receipt, but nothing in the app could set it: the agent
// panel hardcoded a step budget and the dial never left the API. A knob only
// the API can turn is not a knob.
//
// Color is verdict-only in this app, so the levels read by weight and
// hairline rather than hue. The budget is the honest consequence of the choice
// and is shown with the choice, not hidden behind it.
//
// The dial has two parameters and each route enforces the one it actually has:
// an agent spends steps, a selection loop spends candidates. The control shows
// whichever the surface it sits on will really spend, because showing a step
// count on a route with no step loop is a number the run cannot honor.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// Which budget the surface hosting this dial actually enforces.
enum EffortConsequence { steps, candidates }

/// A named dial and the budgets it nominates. Mirrors harness/effort.py
/// (`EFFORTS` and `CANDIDATE_BUDGET`); the engine remains the authority and
/// re-resolves whatever is sent.
enum EffortLevel {
  low('low', 4, 1, 4),
  standard('standard', 8, 4, 16),
  high('high', 12, 8, 32),
  ultra('ultra', 12, 16, 64);

  const EffortLevel(this.wire, this.maxSteps, this.initialN, this.maxN);

  /// The value sent as `effort`. The engine names its own fallback if it
  /// does not recognize this, so a newer app cannot silently downgrade.
  final String wire;

  /// The step budget this level nominates. `ultra` matches `high` on steps and
  /// differs by candidates, so on a step surface the two show the same number
  /// rather than implying a difference the run will not produce.
  final int maxSteps;

  /// The starting batch a selection loop generates before it raises N.
  final int initialN;

  /// The candidate ceiling. This is where `ultra` separates from `high`.
  final int maxN;

  int budgetFor(EffortConsequence c) =>
      c == EffortConsequence.candidates ? maxN : maxSteps;

  String labelFor(EffortConsequence c) => c == EffortConsequence.candidates
      ? '$maxN candidates'
      : '$maxSteps steps';

  static EffortLevel fromWire(String? value) => EffortLevel.values.firstWhere(
        (level) => level.wire == value,
        orElse: () => EffortLevel.standard,
      );
}

class EffortDial extends StatelessWidget {
  final EffortLevel value;
  final ValueChanged<EffortLevel> onChanged;

  /// Disabled while a run is in flight: changing the dial mid-run would
  /// describe a run that never happened.
  final bool enabled;

  /// The budget this surface enforces. Steps by default, because that is what
  /// the agent panel this control was built for spends.
  final EffortConsequence consequence;

  const EffortDial({
    super.key,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.consequence = EffortConsequence.steps,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Semantics(
      label: 'Model effort',
      value: '${value.wire}, ${value.labelFor(consequence)}',
      // Wrap, not Row: the gate strip this sits in is itself a Wrap, and a
      // fixed Row here overflowed a narrow viewport by a fraction of a pixel
      // rather than reflowing with everything around it.
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text('effort',
              style: TextStyle(
                  fontFamily: t.monoFamily, fontSize: 11, color: t.inkFaint)),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: t.line),
              borderRadius: BorderRadius.circular(2),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final level in EffortLevel.values)
                  _Segment(
                    level: level,
                    selected: level == value,
                    enabled: enabled,
                    onTap: () => onChanged(level),
                  ),
              ],
            ),
          ),
          Text(value.labelFor(consequence),
              style: TextStyle(
                  fontFamily: t.monoFamily, fontSize: 11, color: t.inkFaint)),
        ],
      ),
    );
  }
}

class _Segment extends StatelessWidget {
  final EffortLevel level;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  const _Segment({
    required this.level,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final ink = !enabled
        ? t.inkFaint
        : selected
            ? t.ink
            : t.inkMuted;
    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      label: level.wire,
      child: InkWell(
        onTap: enabled ? onTap : null,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: selected ? t.ground2 : null,
            border: Border(
              left: BorderSide(
                color: level == EffortLevel.values.first
                    ? Colors.transparent
                    : t.hairline,
              ),
            ),
          ),
          child: Text(
            level.wire,
            style: TextStyle(
              fontFamily: t.monoFamily,
              fontSize: 11,
              color: ink,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
            ),
          ),
        ),
      ),
    );
  }
}
