// nav_group.dart -- one section of the side rail: the group header and
// its destination rows, rendered straight from the frozen catalog.
import 'package:flutter/material.dart';

import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';
import 'rail_item.dart';

class NavGroup extends StatelessWidget {
  final String label;
  final List<DestinationSpec> destinations;
  final DestinationId selected;
  final bool collapsed;
  final ValueChanged<DestinationId> onSelect;

  const NavGroup({
    super.key,
    required this.label,
    required this.destinations,
    required this.selected,
    required this.collapsed,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (collapsed)
          Container(
            height: 1,
            margin: const EdgeInsets.fromLTRB(
                FwLayout.s3, FwLayout.s3, FwLayout.s3, FwLayout.s2),
            color: t.hairline,
          )
        else
          Padding(
            padding: EdgeInsets.fromLTRB(
                FwLayout.s3, FwLayout.s2, FwLayout.s3, 5),
            child: Text(label.toUpperCase(),
                style: fwKicker(t, size: 9, color: t.inkFaint)),
          ),
        for (final spec in destinations)
          RailItem(
            key: ValueKey('rail-${spec.id.name}'),
            label: spec.label,
            code: spec.abbr,
            selected: spec.id == selected,
            collapsed: collapsed,
            onTap: () => onSelect(spec.id),
          ),
      ],
    );
  }
}
