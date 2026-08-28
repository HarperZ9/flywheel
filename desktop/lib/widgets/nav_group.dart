// nav_group.dart -- one section of the side rail: the group header and
// its destination rows, rendered straight from the frozen catalog.
//
// When foldable (the drawer), the header is a tappable toggle that
// shows or hides the group's destinations. The rail itself never
// folds groups; it uses the collapsed/compact mode instead.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';
import 'rail_item.dart';

class NavGroup extends StatefulWidget {
  final String label;
  final List<DestinationSpec> destinations;
  final DestinationId selected;
  final bool collapsed;
  final bool foldable;
  final ValueChanged<DestinationId> onSelect;

  const NavGroup({
    super.key,
    required this.label,
    required this.destinations,
    required this.selected,
    required this.collapsed,
    this.foldable = false,
    required this.onSelect,
  });

  @override
  State<NavGroup> createState() => _NavGroupState();
}

class _NavGroupState extends State<NavGroup> {
  bool _folded = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final expanded = !widget.foldable || !_folded;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.collapsed)
          Container(
            height: 1,
            margin: const EdgeInsets.fromLTRB(
                FwLayout.s3, FwLayout.s3, FwLayout.s3, FwLayout.s2),
            color: t.hairline,
          )
        else if (widget.foldable)
          _foldHeader(t, expanded)
        else
          Padding(
            padding: EdgeInsets.fromLTRB(
                FwLayout.s3, FwLayout.s2, FwLayout.s3, 5),
            child: Text(widget.label.toUpperCase(),
                style: fwKicker(t, size: 9, color: t.inkFaint)),
          ),
        if (expanded)
          for (final spec in widget.destinations)
            RailItem(
              key: ValueKey('rail-${spec.id.name}'),
              label: spec.label,
              code: spec.abbr,
              selected: spec.id == widget.selected,
              collapsed: widget.collapsed,
              onTap: () => widget.onSelect(spec.id),
            ),
      ],
    );
  }

  Widget _foldHeader(FwTokens t, bool expanded) {
    final active =
        widget.destinations.any((d) => d.id == widget.selected);
    return AccessibleAction(
      semanticLabel:
          '${expanded ? "Collapse" : "Expand"} ${widget.label} group',
      onActivate: () => setState(() => _folded = !_folded),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            FwLayout.s3, FwLayout.s3, FwLayout.s3, FwLayout.s1),
        child: Row(children: [
          Text(widget.label.toUpperCase(),
              style: fwKicker(t,
                  size: 9.5, color: active ? t.inkSoft : t.inkFaint)),
          if (!expanded) ...[
            const SizedBox(width: FwLayout.s2),
            Text('${widget.destinations.length}',
                style: fwMono(t, size: 10, color: t.inkFaint)),
          ],
          const Spacer(),
          Icon(
            expanded ? Icons.expand_less : Icons.expand_more,
            size: 14,
            color: t.inkFaint,
          ),
        ]),
      ),
    );
  }
}
