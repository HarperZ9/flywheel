// appearance_panel.dart — the user's look, their choice. The canon pair is
// the shipped default, not a cage: text and mono families and a UI scale
// are the user's to set, persisted locally. Color keeps meaning a verdict
// under every taste; that rule is what keeps the surface readable, so it
// is the one thing not on the menu.

import 'package:flutter/material.dart';

import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

const kTextChoices = <String?>[
  null, // canon: Hanken Grotesk
  'Segoe UI',
  'Georgia',
  'Cambria',
  'Verdana',
  'Arial',
  'Times New Roman',
];

const kMonoChoices = <String?>[
  null, // canon: Conso
  'Consolas',
  'Cascadia Mono',
  'Courier New',
  'Lucida Console',
];

Future<void> showAppearancePanel(BuildContext context,
    DesktopSettings settings, VoidCallback onChanged) {
  return showDialog(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: ctx.fw.ground,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: _AppearanceForm(settings: settings, onChanged: onChanged),
        ),
      ),
    ),
  );
}

class _AppearanceForm extends StatefulWidget {
  final DesktopSettings settings;
  final VoidCallback onChanged;
  const _AppearanceForm({required this.settings, required this.onChanged});

  @override
  State<_AppearanceForm> createState() => _AppearanceFormState();
}

class _AppearanceFormState extends State<_AppearanceForm> {
  void _apply(void Function() mutate) {
    setState(mutate);
    widget.settings.save();
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final s = widget.settings;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('appearance', hot: true),
        const SizedBox(height: FwLayout.s2),
        Text('Your surface, your type.',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: FwLayout.s2),
        Text(
            'System fonts must be installed to take effect; a missing '
            'family falls back silently. Color stays a verdict under '
            'every taste.',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: FwLayout.s4),
        _fontRow(t, 'text', s.textFamily, kTextChoices, 'Hanken Grotesk',
            (v) => _apply(() => s.textFamily = v)),
        const SizedBox(height: FwLayout.s3),
        _fontRow(t, 'mono', s.monoFamily, kMonoChoices, 'Conso',
            (v) => _apply(() => s.monoFamily = v)),
        const SizedBox(height: FwLayout.s4),
        Row(children: [
          const Kicker('ui scale'),
          Expanded(
            child: Slider(
              value: s.uiScale.clamp(0.85, 1.3),
              min: 0.85,
              max: 1.3,
              divisions: 9,
              onChanged: (v) =>
                  _apply(() => s.uiScale = (v * 20).round() / 20),
            ),
          ),
          Text('${(s.uiScale * 100).round()}%', style: fwMono(t, size: 12)),
        ]),
        const SizedBox(height: FwLayout.s4),
        Row(
          children: [
            OutlinedButton(
              onPressed: () => _apply(() {
                s.textFamily = null;
                s.monoFamily = null;
                s.uiScale = 1.0;
              }),
              child: const Text('Reset to canon'),
            ),
            const Spacer(),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Done'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _fontRow(FwTokens t, String label, String? value,
      List<String?> choices, String canonName, ValueChanged<String?> onPick) {
    return Row(children: [
      SizedBox(width: 56, child: Kicker(label)),
      const SizedBox(width: FwLayout.s3),
      Expanded(
        child: DropdownButton<String?>(
          value: choices.contains(value) ? value : null,
          isExpanded: true,
          underline: const SizedBox(),
          style: fwMono(t, size: 12.5, color: t.inkSoft),
          items: [
            for (final c in choices)
              DropdownMenuItem<String?>(
                value: c,
                child: Text(c ?? '$canonName (canon)',
                    style: TextStyle(
                        fontFamily: c ?? canonName,
                        fontSize: 13,
                        color: t.inkSoft)),
              ),
          ],
          onChanged: onPick,
        ),
      ),
    ]);
  }
}
