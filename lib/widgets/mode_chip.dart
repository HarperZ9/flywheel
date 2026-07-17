// mode_chip.dart — a small mono toggle pill for switching a view between
// modes (chat|agent, roster|detail). Active state is carried by ink weight
// and border, never by color: verdict hues stay reserved for verdicts.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

class FwModeChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;
  const FwModeChip(
      {super.key,
      required this.label,
      required this.active,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: active ? t.inkMuted : t.hairline),
        ),
        child: Text(label,
            style: fwMono(t, size: 10.5, color: active ? t.ink : t.inkFaint)),
      ),
    );
  }
}
