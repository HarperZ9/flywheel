// shell_rail.dart -- the shell's navigation rail: search field, the five
// catalog groups, theme and appearance actions, and the keyboard-adjustable
// resize handle. The search query is rail-local state; typing re-filters
// the groups immediately.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';
import 'nav_group.dart';
import 'nav_search_field.dart';
import 'rail_resizer.dart';

class ShellRail extends StatefulWidget {
  final bool collapsed;
  final double width;
  final DestinationId selected;
  final ValueChanged<DestinationId> onGo;
  final ValueChanged<double> onResize;
  final VoidCallback onToggleCollapse;
  final VoidCallback onToggleTheme;
  final VoidCallback onOpenAppearance;
  final VoidCallback onOpenRecovery;

  const ShellRail({
    super.key,
    required this.collapsed,
    required this.width,
    required this.selected,
    required this.onGo,
    required this.onResize,
    required this.onToggleCollapse,
    required this.onToggleTheme,
    required this.onOpenAppearance,
    required this.onOpenRecovery,
  });

  @override
  State<ShellRail> createState() => _ShellRailState();
}

class _ShellRailState extends State<ShellRail> {
  final TextEditingController _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final q = _query.trim().toLowerCase();
    bool matches(DestinationSpec spec) =>
        q.isEmpty || spec.label.toLowerCase().contains(q);
    final groups = <String, List<DestinationSpec>>{};
    for (final spec in destinationCatalog) {
      if (matches(spec)) (groups[spec.group.name] ??= []).add(spec);
    }
    final rail = AnimatedContainer(
      duration: Duration.zero,
      width: widget.collapsed ? 52.0 : widget.width.clamp(148.0, 320.0),
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(context),
          if (!widget.collapsed)
            NavSearchField(
              controller: _search,
              onChanged: (value) => setState(() => _query = value),
            ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 4),
              children: [
                for (final entry in groups.entries)
                  NavGroup(
                    label: entry.key,
                    destinations: entry.value,
                    selected: widget.selected,
                    collapsed: widget.collapsed,
                    onSelect: widget.onGo,
                  ),
                if (groups.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text('No destination matches.',
                        style: TextStyle(fontSize: 12, color: t.inkFaint)),
                  ),
              ],
            ),
          ),
          _footer(context),
        ],
      ),
    );
    if (widget.collapsed) return rail;
    return Stack(children: [
      rail,
      Positioned(
        right: 0,
        top: 0,
        bottom: 0,
        width: 6,
        child: RailResizer(
            width: widget.width.clamp(148.0, 320.0),
            onResize: widget.onResize),
      ),
    ]);
  }

  Widget _header(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: EdgeInsets.symmetric(
          horizontal: widget.collapsed ? 8 : 12, vertical: 12),
      child: Row(
        mainAxisAlignment: widget.collapsed
            ? MainAxisAlignment.center
            : MainAxisAlignment.start,
        children: [
          if (!widget.collapsed) ...[
            Expanded(
              child: Text('Flywheel',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w700,
                      color: t.ink)),
            ),
            AccessibleAction(
              semanticLabel: 'Collapse navigation rail',
              onActivate: widget.onToggleCollapse,
              child: Icon(Icons.chevron_left, size: 15, color: t.inkFaint),
            ),
          ] else
            AccessibleAction(
              semanticLabel: 'Expand navigation rail',
              onActivate: widget.onToggleCollapse,
              child: Icon(Icons.chevron_right, size: 15, color: t.inkFaint),
            ),
        ],
      ),
    );
  }

  Widget _footer(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Row(children: [
        AccessibleAction(
          semanticLabel: 'Toggle theme',
          onActivate: widget.onToggleTheme,
          child: Icon(Icons.contrast, size: 15, color: t.inkFaint),
        ),
        const SizedBox(width: 8),
        AccessibleAction(
          semanticLabel: 'Open recovery center',
          onActivate: widget.onOpenRecovery,
          child: Icon(Icons.restore_rounded, size: 15, color: t.inkFaint),
        ),
        const SizedBox(width: 8),
        AccessibleAction(
          semanticLabel: 'Open appearance settings',
          onActivate: widget.onOpenAppearance,
          child: Icon(Icons.tune, size: 15, color: t.inkFaint),
        ),
      ]),
    );
  }
}
