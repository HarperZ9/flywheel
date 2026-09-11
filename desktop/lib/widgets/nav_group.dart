// nav_group.dart -- one section of the side rail: the group header and
// its destination rows, rendered straight from the frozen catalog.
//
// When foldable, the header is a tappable toggle that shows or hides the
// group's destinations. The drawer may fold any group; the desktop rail folds
// the secondary tools/admin group so specialist routes remain findable without
// crowding first-run work paths.
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
  final bool initiallyFolded;
  final ValueChanged<DestinationId> onSelect;

  const NavGroup({
    super.key,
    required this.label,
    required this.destinations,
    required this.selected,
    required this.collapsed,
    this.foldable = false,
    this.initiallyFolded = false,
    required this.onSelect,
  });

  @override
  State<NavGroup> createState() => _NavGroupState();
}

class _NavGroupState extends State<NavGroup> {
  late bool _folded;

  @override
  void initState() {
    super.initState();
    _folded = widget.initiallyFolded;
  }

  @override
  void didUpdateWidget(NavGroup oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.label != widget.label) {
      _folded = widget.initiallyFolded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final active = widget.destinations.any((d) => d.id == widget.selected);
    final expanded = !widget.foldable || active || !_folded;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.collapsed)
          Container(
            height: 1,
            margin: const EdgeInsets.fromLTRB(
              FwLayout.s3,
              FwLayout.s3,
              FwLayout.s3,
              FwLayout.s2,
            ),
            color: t.hairline,
          )
        else if (widget.foldable)
          _foldHeader(t, expanded)
        else
          Padding(
            padding: EdgeInsets.fromLTRB(
              FwLayout.s3,
              FwLayout.s2,
              FwLayout.s3,
              5,
            ),
            child: Text(
              widget.label.toUpperCase(),
              style: fwKicker(t, size: 9, color: t.inkFaint),
            ),
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
    final active = widget.destinations.any((d) => d.id == widget.selected);
    return AccessibleAction(
      semanticLabel:
          '${expanded ? "Collapse" : "Expand"} ${widget.label} group',
      onActivate: () => setState(() => _folded = !_folded),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          FwLayout.s3,
          FwLayout.s3,
          FwLayout.s3,
          FwLayout.s1,
        ),
        child: Row(
          children: [
            Flexible(
              child: Text(
                widget.label.toUpperCase(),
                overflow: TextOverflow.ellipsis,
                style: fwKicker(
                  t,
                  size: 9.5,
                  color: active ? t.inkSoft : t.inkFaint,
                ),
              ),
            ),
            if (!expanded) ...[
              const SizedBox(width: FwLayout.s2),
              Text(
                '${widget.destinations.length}',
                style: fwMono(t, size: 10, color: t.inkFaint),
              ),
            ],
            const SizedBox(width: FwLayout.s2),
            Icon(
              expanded ? Icons.expand_less : Icons.expand_more,
              size: 14,
              color: t.inkFaint,
            ),
          ],
        ),
      ),
    );
  }
}
