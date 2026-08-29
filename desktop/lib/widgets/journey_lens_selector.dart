import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';

const _lenses = [JourneyLens.rescue, JourneyLens.diagnose, JourneyLens.verify];

String lensName(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      _ => 'Verify',
    };

IconData lensIcon(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => Icons.restore,
      JourneyLens.diagnose => Icons.manage_search,
      _ => Icons.verified_user_outlined,
    };

class JourneyLensSelector extends StatefulWidget {
  const JourneyLensSelector({
    super.key,
    required this.selectedLens,
    required this.onSelected,
    this.enabled = true,
  });
  final JourneyLens selectedLens;
  final Future<void> Function(JourneyLens) onSelected;
  final bool enabled;

  @override
  State<JourneyLensSelector> createState() => _JourneyLensSelectorState();
}

class _JourneyLensSelectorState extends State<JourneyLensSelector> {
  late final List<FocusNode> _nodes;

  @override
  void initState() {
    super.initState();
    _nodes = List.generate(_lenses.length, (_) => FocusNode());
  }

  @override
  void dispose() {
    for (final node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _select(int index) {
    if (!widget.enabled) return;
    final next = index.clamp(0, _lenses.length - 1);
    _nodes[next].requestFocus();
    widget.onSelected(_lenses[next]);
  }

  Widget _button(BuildContext context, int index) {
    final lens = _lenses[index];
    final selected = lens == widget.selectedLens;
    final t = context.fw;
    final style = ButtonStyle(
      minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
      padding: const WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: FwLayout.s3, vertical: FwLayout.s2)),
      foregroundColor: WidgetStatePropertyAll(t.inkSoft),
      backgroundColor: WidgetStatePropertyAll(selected ? t.ground2 : t.ground),
      shape: WidgetStatePropertyAll(RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall))),
      side: WidgetStateProperty.resolveWith((states) => BorderSide(
          color: states.contains(WidgetState.focused)
              ? t.ink
              : selected
                  ? t.inkMuted
                  : t.line,
          width: states.contains(WidgetState.focused) ? 2 : 1)),
    );
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () =>
            _select(index - 1),
        const SingleActivator(LogicalKeyboardKey.arrowUp): () =>
            _select(index - 1),
        const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
            _select(index + 1),
        const SingleActivator(LogicalKeyboardKey.arrowDown): () =>
            _select(index + 1),
        const SingleActivator(LogicalKeyboardKey.home): () => _select(0),
        const SingleActivator(LogicalKeyboardKey.end): () =>
            _select(_lenses.length - 1),
      },
      child: Semantics(
        label: lensName(lens),
        button: true,
        selected: selected,
        enabled: widget.enabled,
        onTap: widget.enabled ? () => widget.onSelected(lens) : null,
        excludeSemantics: true,
        child: OutlinedButton.icon(
          key: ValueKey('journey-lens-${lens.name}'),
          focusNode: _nodes[index],
          onPressed: widget.enabled ? () => widget.onSelected(lens) : null,
          style: style,
          icon: Icon(lensIcon(lens), size: 18),
          label: Text(lensName(lens)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final buttons = [
            for (var index = 0; index < _lenses.length; index++)
              _button(context, index),
          ];
          if (constraints.maxWidth < 480) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final (index, button) in buttons.indexed) ...[
                  if (index > 0) const SizedBox(height: FwLayout.s2),
                  button,
                ],
              ],
            );
          }
          return Row(children: [
            for (final (index, button) in buttons.indexed) ...[
              if (index > 0) const SizedBox(width: FwLayout.s2),
              Expanded(child: button),
            ],
          ]);
        },
      );
}
