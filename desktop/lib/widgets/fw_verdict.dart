// fw_verdict.dart -- the verdict primitives. The ONLY colored chips in
// the system: a pill for labeled verdicts, a dot for dense rows. Status
// maps through the verdict palette (verified / drift / unverifiable).
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
        color: c.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      child: Text(label.toUpperCase(),
          style: fwKicker(t, color: c, size: 10).copyWith(letterSpacing: 1.4)),
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
