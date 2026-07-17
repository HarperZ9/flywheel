// composer_controls.dart — the small labeled dropdown and grant checkbox
// the run composers share. A grant is a checkbox the user flips per run,
// never a default; the label says exactly what it allows.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class LabeledPicker extends StatelessWidget {
  final String label;
  final String? value;
  final List<String> options;
  final ValueChanged<String?> onChanged;
  const LabeledPicker(
      {super.key,
      required this.label,
      required this.value,
      required this.options,
      required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Kicker(label),
        const SizedBox(width: FwLayout.s2),
        DropdownButton<String>(
          value: options.contains(value) ? value : null,
          underline: const SizedBox(),
          style: fwMono(t, size: 12, color: t.inkSoft),
          items: [
            for (final o in options) DropdownMenuItem(value: o, child: Text(o)),
          ],
          onChanged: onChanged,
        ),
      ],
    );
  }
}

class GrantCheckbox extends StatelessWidget {
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  const GrantCheckbox(
      {super.key,
      required this.label,
      required this.value,
      required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Checkbox(
            value: value,
            onChanged: (v) => onChanged(v ?? false),
            visualDensity: VisualDensity.compact),
        Text('allow $label', style: fwMono(t, size: 11.5, color: t.inkMuted)),
      ],
    );
  }
}
