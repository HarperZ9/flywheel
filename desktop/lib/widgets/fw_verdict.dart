// fw_verdict.dart -- the verdict primitives. The ONLY colored chips in
// the system: a pill for labeled verdicts, a dot for dense rows. Status
// maps through the verdict palette (verified / drift / unverifiable).
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// A verdict chip: tinted ground, hairline border, mono uppercase label.
class VerdictPill extends StatelessWidget {
  final String label;
  final String status;
  const VerdictPill(this.label, {super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final c = t.statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: pillTintAlpha),
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      child: Text(label.toUpperCase(),
          style: fwKicker(t, color: pillInk(t, c), size: 10)
              .copyWith(letterSpacing: 1.4)),
    );
  }
}

/// A small verdict dot for dense rows.
class VerdictDot extends StatelessWidget {
  final String status;
  final double size;
  const VerdictDot(this.status, {super.key, this.size = 8});

  @override
  Widget build(BuildContext context) {
    final c = context.fw.statusColor(status);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: c, shape: BoxShape.circle),
    );
  }
}

/// The pill's fill: its verdict hue at this alpha over whatever is behind it.
const pillTintAlpha = 0.10;

/// WCAG AA for small text.
const pillMinContrast = 4.5;

double _luminance(Color c) {
  double linear(double channel) => channel <= 0.03928
      ? channel / 12.92
      : math.pow((channel + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b);
}

/// The WCAG contrast ratio of two opaque colors.
double contrastRatio(Color a, Color b) {
  final la = _luminance(a), lb = _luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// The two grounds a pill sits on: the page ground and a card panel over it,
/// each under the pill's own tint.
List<Color> pillGrounds(FwTokens t, Color hue) => [
      t.ground,
      Color.alphaBlend(t.panel, t.ground),
    ].map((g) => Color.alphaBlend(hue.withValues(alpha: pillTintAlpha), g)).toList();

/// The pill's text color: its verdict hue, moved toward the ink only as far
/// as small text needs to reach 4.5:1 on both grounds. The hue stays, so the
/// verdict still reads by color; a hue that already passes is unchanged.
Color pillInk(FwTokens t, Color hue) {
  final grounds = pillGrounds(t, hue);
  for (var step = 0; step <= 20; step++) {
    final ink = Color.lerp(hue, t.ink, step / 20)!;
    if (grounds.every((g) => contrastRatio(ink, g) >= pillMinContrast)) {
      return ink;
    }
  }
  return t.ink;
}
