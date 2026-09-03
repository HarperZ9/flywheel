// effort_dial.dart — the one knob, as a control the operator can reach.
//
// The engine has carried four named dials since July and stamps the resolved
// one into every run receipt, but nothing in the app could set it: the agent
// panel hardcoded a step budget and the dial never left the API. A knob only
// the API can turn is not a knob.
//
// Color is verdict-only in this app, so the levels read by weight and
// hairline rather than hue. The step budget is the honest consequence of the
// choice and is shown with the choice, not hidden behind it.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// A named dial and the step budget it nominates. Mirrors harness/effort.py;
/// the engine remains the authority and re-resolves whatever is sent.
enum EffortLevel {
  low('low', 4),
  standard('standard', 8),
  high('high', 12),
  ultra('ultra', 12);

  const EffortLevel(this.wire, this.maxSteps);

  /// The value sent as `effort`. The engine names its own fallback if it
  /// does not recognize this, so a newer app cannot silently downgrade.
  final String wire;

  /// The step budget this level nominates. `ultra` matches `high` on steps
  /// and differs by candidate count, which this control does not set, so the
  /// two deliberately show the same number rather than implying otherwise.
  final int maxSteps;

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

  const EffortDial({
    super.key,
    required this.value,
    required this.onChanged,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Semantics(
      label: 'Model effort',
      value: '${value.wire}, ${value.maxSteps} steps',
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
          Text('${value.maxSteps} steps',
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
