// side_rail.dart — the navigation sidebar. Collapsible so the working
// surface stays the largest thing on screen: full shows numbered labels,
// collapsed shows a thin mono-code rail. Items, the resize handle, and
// the footer buttons are all keyboard-activatable semantic controls;
// the pieces live in rail_item.dart and rail_resizer.dart.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../theme/flywheel_theme.dart';
import 'aperture.dart';
import 'rail_item.dart';
import 'rail_resizer.dart';

class RailDestination {
  final String label;
  final String abbr;

  /// The goal group this destination belongs to (Start / Do / Know / Advanced).
  /// The rail draws a section header when the group changes, so the nav reads as
  /// "what did you come to do", not a flat wall of subsystems.
  final String group;
  const RailDestination(this.label, {this.abbr = '', this.group = ''});
  String get code => abbr.isNotEmpty
      ? abbr
      : (label.length >= 2 ? label.substring(0, 2) : label).toUpperCase();
}

class SideRail extends StatelessWidget {
  final List<RailDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;
  final bool collapsed;
  final double width;
  final ValueChanged<double>? onResize;
  final VoidCallback onToggleCollapse;
  final VoidCallback? onOpenAppearance;

  /// Injectable focus nodes per destination index (tests, or callers that
  /// own focus order). Null entries use the item's own node.
  final Map<int, FocusNode>? itemFocusNodes;

  const SideRail({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    required this.themeMode,
    required this.onToggleTheme,
    required this.collapsed,
    this.width = 172,
    this.onResize,
    required this.onToggleCollapse,
    this.onOpenAppearance,
    this.itemFocusNodes,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final w = collapsed ? 52.0 : width.clamp(148.0, 320.0);
    final rail = AnimatedContainer(
      duration: onResize != null && !collapsed
          ? Duration.zero      // no easing while the user is dragging
          : FwLayout.transition,
      width: w,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(t),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: FwLayout.s1),
              children: [
                for (var i = 0; i < destinations.length; i++) ...[
                  if (_startsGroup(i)) ...[
                    if (collapsed)
                      Container(
                        height: 1,
                        margin: const EdgeInsets.fromLTRB(
                            FwLayout.s3, FwLayout.s3, FwLayout.s3, FwLayout.s2),
                        color: t.hairline,
                      )
                    else
                      _GroupHeader(destinations[i].group, first: i == 0),
                  ],
                  RailItem(
                    key: ValueKey('rail-${destinations[i].label}'),
                    index: i,
                    dest: destinations[i],
                    selected: i == selectedIndex,
                    collapsed: collapsed,
                    onTap: () => onSelect(i),
                    focusNode: itemFocusNodes?[i],
                  ),
                ],
              ],
            ),
          ),
          _footer(t),
        ],
      ),
    );
    if (collapsed || onResize == null) return rail;
    // a focusable drag handle on the right edge widens or narrows the rail
    return Stack(children: [
      rail,
      Positioned(
        right: 0,
        top: 0,
        bottom: 0,
        width: 6,
        child: RailResizer(width: w, onResize: onResize!),
      ),
    ]);
  }

  bool _startsGroup(int i) =>
      destinations[i].group.isNotEmpty &&
      (i == 0 || destinations[i - 1].group != destinations[i].group);

  Widget _header(FwTokens t) {
    return Padding(
      padding: EdgeInsets.symmetric(
          horizontal: collapsed ? FwLayout.s2 : FwLayout.s3,
          vertical: FwLayout.s3),
      child: Row(
        mainAxisAlignment:
            collapsed ? MainAxisAlignment.center : MainAxisAlignment.start,
        children: [
          const ApertureMark(size: 26),
          if (!collapsed) ...[
            const SizedBox(width: FwLayout.s2),
            Expanded(
              child: Text('Flywheel',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w700,
                      color: t.ink)),
            ),
            _iconBtn(t, Icons.chevron_left, onToggleCollapse,
                'Collapse navigation rail'),
          ],
        ],
      ),
    );
  }

  Widget _footer(FwTokens t) {
    if (collapsed) {
      return Padding(
        padding: const EdgeInsets.all(FwLayout.s2),
        child: Column(
          children: [
            _iconBtn(t, Icons.chevron_right, onToggleCollapse,
                'Expand navigation rail'),
            const SizedBox(height: FwLayout.s2),
            _iconBtn(t, _themeIcon, onToggleTheme, 'Toggle theme'),
            if (onOpenAppearance != null) ...[
              const SizedBox(height: FwLayout.s2),
              _iconBtn(t, Icons.tune, onOpenAppearance!, 'Appearance'),
            ],
          ],
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s2),
      child: Row(
        children: [
          Expanded(
              child: _ThemeToggle(mode: themeMode, onToggle: onToggleTheme)),
          if (onOpenAppearance != null) ...[
            const SizedBox(width: FwLayout.s2),
            _iconBtn(t, Icons.tune, onOpenAppearance!, 'Appearance'),
          ],
        ],
      ),
    );
  }

  IconData get _themeIcon => switch (themeMode) {
        ThemeMode.light => Icons.light_mode_outlined,
        ThemeMode.dark => Icons.dark_mode_outlined,
        ThemeMode.system => Icons.contrast,
      };

  Widget _iconBtn(FwTokens t, IconData icon, VoidCallback? onTap,
          String label) {
    return AccessibleAction(
      semanticLabel: label,
      tooltip: label,
      onActivate: onTap,
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: Icon(icon, size: 15, color: t.inkFaint),
      ),
    );
  }
}

class _GroupHeader extends StatelessWidget {
  final String label;
  final bool first;
  const _GroupHeader(this.label, {this.first = false});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          FwLayout.s3, first ? FwLayout.s2 : FwLayout.s4, FwLayout.s3, 5),
      child: Text(label.toUpperCase(),
          style: fwKicker(t, size: 9, color: t.inkFaint)),
    );
  }
}

class _ThemeToggle extends StatelessWidget {
  final ThemeMode mode;
  final VoidCallback onToggle;
  const _ThemeToggle({required this.mode, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final label = switch (mode) {
      ThemeMode.system => 'theme: system',
      ThemeMode.light => 'theme: light',
      ThemeMode.dark => 'theme: dark',
    };
    return AccessibleAction(
      semanticLabel: label,
      onActivate: onToggle,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s2, vertical: 6),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
          border: Border.all(color: t.line),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
                switch (mode) {
                  ThemeMode.light => Icons.light_mode_outlined,
                  ThemeMode.dark => Icons.dark_mode_outlined,
                  ThemeMode.system => Icons.contrast,
                },
                size: 13,
                color: t.inkMuted),
            const SizedBox(width: FwLayout.s2),
            Flexible(
              child: Text(label,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 10, color: t.inkMuted)),
            ),
          ],
        ),
      ),
    );
  }
}
