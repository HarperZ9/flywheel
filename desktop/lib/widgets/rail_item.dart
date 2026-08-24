// rail_item.dart -- one navigation destination on the side rail.
// A semantic, keyboard-activatable button: selection is announced, the
// label is the accessible name, and Enter or Space selects. Takes
// primitives, so it never couples to the rail that hosts it.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../theme/flywheel_theme.dart';

class RailItem extends StatefulWidget {
  final String label;
  final String code;
  final bool selected;
  final bool collapsed;
  final VoidCallback onTap;

  /// Injectable focus node (tests, or callers that own focus order).
  final FocusNode? focusNode;

  const RailItem({
    super.key,
    required this.label,
    required this.code,
    required this.selected,
    required this.collapsed,
    required this.onTap,
    this.focusNode,
  });

  @override
  State<RailItem> createState() => _RailItemState();
}

class _RailItemState extends State<RailItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final selected = widget.selected;
    final bg = selected
        ? t.panel
        : _hover
            ? t.panel.withValues(alpha: 0.5)
            : Colors.transparent;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AccessibleAction(
        semanticLabel: widget.label,
        selected: selected,
        onActivate: widget.onTap,
        focusNode: widget.focusNode,
        tooltip: widget.collapsed ? widget.label : null,
        child: Container(
          margin: const EdgeInsets.symmetric(
              horizontal: FwLayout.s1, vertical: 1),
          padding: EdgeInsets.symmetric(
              horizontal: widget.collapsed ? 0 : FwLayout.s2, vertical: 6),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          ),
          child: widget.collapsed
              ? _compact(t, selected)
              : _full(t, selected),
        ),
      ),
    );
  }

  Widget _compact(FwTokens t, bool selected) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 2.5,
          height: 14,
          decoration: BoxDecoration(
            color: selected ? t.ink : Colors.transparent,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 4),
        Text(widget.code,
            style: fwKicker(t,
                size: 9.5, color: selected ? t.ink : t.inkMuted)),
      ],
    );
  }

  Widget _full(FwTokens t, bool selected) {
    return Row(
      children: [
        Container(
          width: 2.5,
          height: 13,
          decoration: BoxDecoration(
            color: selected ? t.ink : Colors.transparent,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text(widget.label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  color: selected ? t.ink : t.inkMuted)),
        ),
      ],
    );
  }
}
